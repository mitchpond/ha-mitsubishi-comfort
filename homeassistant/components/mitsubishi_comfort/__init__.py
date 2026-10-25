"""Mitsubishi Comfort integration for Home Assistant."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.util.json import load_json
from homeassistant.helpers.json import save_json

from .lib import CloudIndoorUnit, IndoorUnit, KumoStation, MitsubishiCloudAccount
from .lib.discovery import probe_candidate_ips
from .lib.exceptions import AuthenticationError, DeviceConnectionError
from .lib.types import DeviceInfo

from .const import CONF_CONNECT_TIMEOUT, CONF_RESPONSE_TIMEOUT, DOMAIN, PLATFORMS
from .coordinator import MitsubishiComfortCoordinator

_LOGGER = logging.getLogger(__name__)

CREDENTIAL_CACHE = "mitsubishi_comfort_devices.json"

MitsubishiComfortConfigEntry = ConfigEntry


def _load_cached_credentials(hass: HomeAssistant) -> dict[str, dict]:
    """Load cached device credentials (address, password, cryptoSerial).

    Returns dict of serial -> {address, password, crypto_serial, label, ...}.
    Also imports from legacy kumo_cache.json on first run.
    """
    # Try our own cache first
    try:
        cached = load_json(hass.config.path(CREDENTIAL_CACHE))
        if isinstance(cached, dict) and cached:
            _LOGGER.info("Loaded credentials for %d devices from cache", len(cached))
            return cached
    except Exception:
        pass

    # Fall back to legacy kumo cache for addresses only
    addresses: dict[str, str] = {}
    try:
        kumo = load_json(hass.config.path("kumo_cache.json"))
        if isinstance(kumo, list) and len(kumo) >= 3:
            for child in kumo[2].get("children", []):
                for serial, unit in child.get("zoneTable", {}).items():
                    addr = unit.get("address", "")
                    if addr and addr not in ("N/A", "empty"):
                        addresses[serial] = addr
                for grandchild in child.get("children", []):
                    for serial, unit in grandchild.get("zoneTable", {}).items():
                        addr = unit.get("address", "")
                        if addr and addr not in ("N/A", "empty"):
                            addresses[serial] = addr
    except Exception:
        pass

    if addresses:
        _LOGGER.info("Imported %d addresses from legacy kumo cache", len(addresses))
        return {serial: {"address": addr} for serial, addr in addresses.items()}

    return {}


def _make_device(
    info: DeviceInfo, serial: str, connect_timeout: float, response_timeout: float
) -> IndoorUnit | KumoStation:
    cls = IndoorUnit if info.is_indoor_unit else KumoStation
    return cls(
        name=info.label, address=info.address,
        password_b64=info.password, crypto_serial_hex=info.crypto_serial,
        serial=serial, connect_timeout=connect_timeout, response_timeout=response_timeout,
    )


def _save_credentials(hass: HomeAssistant, devices: dict[str, DeviceInfo]) -> None:
    """Save device credentials to cache."""
    cache = {}
    for serial, info in devices.items():
        cache[serial] = {
            "address": info.address,
            "password": info.password,
            "crypto_serial": info.crypto_serial,
            "label": info.label,
            "mac": info.mac,
            "unit_type": info.unit_type,
        }
    save_json(hass.config.path(CREDENTIAL_CACHE), cache)
    _LOGGER.info("Saved credentials for %d devices to cache", len(cache))


def _merge_cached_into_devices(
    devices: dict[str, DeviceInfo], cached: dict[str, dict]
) -> list[str]:
    """Merge cached credentials into discovered devices. Returns list of serials that were updated."""
    updated = []
    for serial, info in devices.items():
        if serial not in cached:
            continue
        c = cached[serial]
        if not info.address and c.get("address"):
            info.address = c["address"]
        if not info.password and c.get("password"):
            info.password = c["password"]
            updated.append(serial)
        if not info.crypto_serial and c.get("crypto_serial"):
            info.crypto_serial = c["crypto_serial"]
    return updated


async def async_setup_entry(hass: HomeAssistant, entry: MitsubishiComfortConfigEntry) -> bool:
    """Set up Mitsubishi Comfort from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    account = MitsubishiCloudAccount(username, password)
    try:
        await account.login()
    except AuthenticationError as ex:
        raise ConfigEntryNotReady(f"Authentication failed: {ex}") from ex
    except DeviceConnectionError as ex:
        raise ConfigEntryNotReady(f"Could not connect to Mitsubishi cloud: {ex}") from ex

    # Load cached credentials
    cached = await hass.async_add_executor_job(_load_cached_credentials, hass)

    # Discover devices — pass cached credentials so Socket.IO is skipped
    # for devices we already have passwords for; cloud_fallback lets devices
    # without local creds be controlled via the cloud API instead
    devices = await account.discover_devices(
        cached_credentials=cached,
        cloud_fallback=True,
    )
    if not devices:
        raise ConfigEntryNotReady("No devices discovered")

    # Merge any remaining cached data (addresses from legacy cache, etc.)
    updated = _merge_cached_into_devices(devices, cached)
    if updated:
        _LOGGER.info("Restored cached credentials for: %s", ", ".join(
            devices[s].label for s in updated
        ))

    # Probe DHCP-discovered IPs for any still-missing addresses
    missing_addr = {s: d for s, d in devices.items() if not d.address}
    if missing_addr:
        dhcp_ips = hass.data.get(f"{DOMAIN}_dhcp_discovered", {})
        if dhcp_ips:
            matched = await probe_candidate_ips(
                missing_addr, list(dhcp_ips.values()), timeout=3.0
            )
            for serial, ip in matched.items():
                devices[serial].address = ip

    # Save credentials for next restart
    await hass.async_add_executor_job(_save_credentials, hass, devices)

    connect_timeout = float(entry.options.get(CONF_CONNECT_TIMEOUT, 1.2))
    response_timeout = float(entry.options.get(CONF_RESPONSE_TIMEOUT, 8.0))

    # Create coordinators for all devices: local if creds are complete,
    # cloud if only a site_id is available, or queue for background retry.
    coordinators: dict[str, MitsubishiComfortCoordinator] = {}
    cloud_serials: list[str] = []
    incomplete_serials: list[str] = []
    for serial, info in devices.items():
        if info.address and info.password and info.crypto_serial:
            device = _make_device(info, serial, connect_timeout, response_timeout)
        elif info.site_id:
            _LOGGER.info(
                "Device %s missing local credentials — using cloud control",
                info.label,
            )
            device = CloudIndoorUnit(info, account)
            cloud_serials.append(serial)
        else:
            incomplete_serials.append(serial)
            _LOGGER.warning(
                "Device %s missing credentials (addr=%s, pw=%s, crypto=%s) — will retry in background",
                info.label,
                bool(info.address),
                bool(info.password),
                bool(info.crypto_serial),
            )
            continue
        coordinators[serial] = MitsubishiComfortCoordinator(hass, device)

    if not coordinators:
        raise ConfigEntryNotReady("No devices have complete or cloud-accessible credentials yet")

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"coordinators": coordinators, "account": account}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Background retry: try to acquire local credentials for cloud-controlled
    # and credential-less devices so they can switch to faster LAN control.
    # A background task, not hass.async_create_task: HA waits for tracked tasks
    # before finishing startup, and this one sleeps and polls for minutes. It is
    # also cancelled automatically when the entry unloads.
    retry_serials = cloud_serials + incomplete_serials
    if retry_serials:
        entry.async_create_background_task(
            hass,
            _retry_incomplete_devices(
                hass, entry, account, devices, retry_serials,
                connect_timeout, response_timeout,
            ),
            f"{DOMAIN}_retry_local_credentials",
        )

    return True


async def _retry_incomplete_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    account: MitsubishiCloudAccount,
    devices: dict[str, DeviceInfo],
    serials_to_retry: list[str],
    connect_timeout: float,
    response_timeout: float,
) -> None:
    """Try to acquire local credentials for cloud-controlled or credential-less devices."""
    for attempt in range(3):
        await asyncio.sleep(30 * (attempt + 1))

        if entry.entry_id not in hass.data.get(DOMAIN, {}):
            return  # Integration was unloaded

        _LOGGER.info(
            "Background retry %d/3 for %d devices awaiting local credentials",
            attempt + 1, len(serials_to_retry),
        )

        # Re-fetch passwords via Socket.IO for devices still missing them
        passwords = await account.get_passwords_via_websocket(
            serials_to_retry, timeout_secs=60,
        )

        newly_complete = []
        for serial in list(serials_to_retry):
            info = devices[serial]
            if serial in passwords and not info.password:
                info.password = passwords[serial]
            if info.address and info.password and info.crypto_serial:
                newly_complete.append(serial)

        if not newly_complete:
            continue

        # Close cloud devices and create local replacements
        entry_data = hass.data[DOMAIN][entry.entry_id]
        coordinators = entry_data["coordinators"]
        for serial in newly_complete:
            info = devices[serial]
            serials_to_retry.remove(serial)
            _LOGGER.info("Device %s acquired local credentials — switching to LAN", info.label)
            old = coordinators.get(serial)
            if old:
                await old.device.close()
            device = _make_device(info, serial, connect_timeout, response_timeout)
            coordinators[serial] = MitsubishiComfortCoordinator(hass, device)

        # Save updated credentials
        await hass.async_add_executor_job(_save_credentials, hass, devices)

        # Reload to register new entities cleanly. Scheduled rather than awaited:
        # unloading the entry cancels its background tasks, including this one.
        hass.config_entries.async_schedule_reload(entry.entry_id)
        return  # The reload will re-run async_setup_entry with full local creds

    if serials_to_retry:
        _LOGGER.info(
            "Devices continuing on cloud control: %s",
            ", ".join(devices[s].label for s in serials_to_retry),
        )


async def async_unload_entry(hass: HomeAssistant, entry: MitsubishiComfortConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id)
        for coordinator in entry_data["coordinators"].values():
            await coordinator.device.close()
        await entry_data["account"].close()
    return unload_ok
