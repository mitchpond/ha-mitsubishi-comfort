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

from .lib import IndoorUnit, KumoStation, MitsubishiCloudAccount
from .lib.discovery import probe_candidate_ips
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
    if not await account.login():
        raise ConfigEntryNotReady("Failed to authenticate with Mitsubishi cloud")

    # Load cached credentials
    cached = await hass.async_add_executor_job(_load_cached_credentials, hass)

    # Discover devices — pass cached credentials so Socket.IO is skipped
    # for devices we already have passwords for
    devices = await account.discover_devices(
        cached_credentials=cached,
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

    # Create coordinators for devices that have full credentials
    coordinators: dict[str, MitsubishiComfortCoordinator] = {}
    incomplete_serials: list[str] = []
    for serial, info in devices.items():
        if not info.address or not info.password or not info.crypto_serial:
            incomplete_serials.append(serial)
            _LOGGER.warning(
                "Device %s missing credentials (addr=%s, pw=%s, crypto=%s) — will retry in background",
                info.label,
                bool(info.address),
                bool(info.password),
                bool(info.crypto_serial),
            )
            continue

        device = _make_device(info, serial, connect_timeout, response_timeout)
        coordinators[serial] = MitsubishiComfortCoordinator(hass, device)

    if not coordinators:
        raise ConfigEntryNotReady("No devices have complete credentials yet")

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinators

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Background retry for incomplete devices
    if incomplete_serials:
        hass.async_create_task(
            _retry_incomplete_devices(
                hass, entry, account, devices, incomplete_serials,
                connect_timeout, response_timeout,
            )
        )

    return True


async def _retry_incomplete_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    account: MitsubishiCloudAccount,
    devices: dict[str, DeviceInfo],
    incomplete_serials: list[str],
    connect_timeout: float,
    response_timeout: float,
) -> None:
    """Retry credential retrieval for devices that were missing passwords."""
    for attempt in range(3):
        await asyncio.sleep(30 * (attempt + 1))

        if entry.entry_id not in hass.data.get(DOMAIN, {}):
            return  # Integration was unloaded

        _LOGGER.info(
            "Background retry %d/3 for %d incomplete devices",
            attempt + 1, len(incomplete_serials),
        )

        # Re-fetch passwords via Socket.IO for just the missing devices
        passwords = await account.get_passwords_via_websocket(
            incomplete_serials, timeout_secs=60,
        )

        newly_complete = []
        for serial in list(incomplete_serials):
            info = devices[serial]
            if serial in passwords and not info.password:
                info.password = passwords[serial]
            if info.address and info.password and info.crypto_serial:
                newly_complete.append(serial)

        if not newly_complete:
            continue

        # Create coordinators and entities for newly complete devices
        coordinators = hass.data[DOMAIN][entry.entry_id]
        for serial in newly_complete:
            info = devices[serial]
            incomplete_serials.remove(serial)
            _LOGGER.info("Device %s now has complete credentials", info.label)

            device = _make_device(info, serial, connect_timeout, response_timeout)
            coordinators[serial] = MitsubishiComfortCoordinator(hass, device)

        # Save updated credentials
        await hass.async_add_executor_job(_save_credentials, hass, devices)

        # Reload the entire entry to pick up new entities cleanly
        await hass.config_entries.async_reload(entry.entry_id)
        return  # The reload will re-run async_setup_entry with all devices

    if incomplete_serials:
        _LOGGER.warning(
            "Could not retrieve credentials for: %s — restart to retry",
            ", ".join(devices[s].label for s in incomplete_serials),
        )


async def async_unload_entry(hass: HomeAssistant, entry: MitsubishiComfortConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinators = hass.data[DOMAIN].pop(entry.entry_id)
        for coordinator in coordinators.values():
            await coordinator.device.close()
    return unload_ok
