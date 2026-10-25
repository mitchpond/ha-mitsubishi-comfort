"""Mitsubishi Comfort integration for Home Assistant."""

import asyncio
import logging
from pathlib import Path
from typing import Any

from mitsubishi_comfort import (
    CloudIndoorUnit,
    IndoorUnit,
    KumoStation,
    MitsubishiCloudAccount,
)
from mitsubishi_comfort.discovery import probe_candidate_ips
from mitsubishi_comfort.exceptions import AuthenticationError, DeviceConnectionError
from mitsubishi_comfort.types import DeviceInfo

from homeassistant.components.dhcp import async_discovered_service_info
from homeassistant.const import CONF_DEVICES, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryError,
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.util.json import load_json

from .const import (
    CONF_CONNECT_TIMEOUT,
    CONF_RESPONSE_TIMEOUT,
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_RESPONSE_TIMEOUT,
    DHCP_MAC_PREFIXES,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import (
    MitsubishiComfortConfigEntry,
    MitsubishiComfortCoordinator,
    MitsubishiComfortData,
)

_LOGGER = logging.getLogger(__name__)

# Credential cache written by earlier versions; migrated into the entry.
LEGACY_CREDENTIAL_CACHE = "mitsubishi_comfort_devices.json"

RETRY_ATTEMPTS = 3
RETRY_DELAY = 30  # seconds, multiplied by the attempt number


def _has_local_credentials(info: DeviceInfo) -> bool:
    """Return whether the device can be controlled over the LAN."""
    return bool(info.address and info.password and info.crypto_serial)


def _make_device(
    info: DeviceInfo, serial: str, connect_timeout: float, response_timeout: float
) -> IndoorUnit | KumoStation:
    """Create a LAN-controlled device."""
    cls = IndoorUnit if info.is_indoor_unit else KumoStation
    return cls(
        name=info.label,
        address=info.address,
        password_b64=info.password,
        crypto_serial_hex=info.crypto_serial,
        serial=serial,
        connect_timeout=connect_timeout,
        response_timeout=response_timeout,
    )


def _load_legacy_credentials(path: str) -> dict[str, Any]:
    """Read the credential cache file written by earlier versions."""
    try:
        cached = load_json(path)
    except HomeAssistantError:
        return {}
    return cached if isinstance(cached, dict) else {}


def _remove_legacy_credentials(path: str) -> None:
    """Delete the old credential cache file once it has been migrated."""
    try:
        Path(path).unlink(missing_ok=True)
    except OSError as err:
        _LOGGER.warning("Could not remove %s: %s", path, err)


def _save_credentials(
    hass: HomeAssistant,
    entry: MitsubishiComfortConfigEntry,
    devices: dict[str, DeviceInfo],
) -> None:
    """Store device credentials in the config entry for the next setup."""
    cache = {
        serial: {
            "address": info.address,
            "password": info.password,
            "crypto_serial": info.crypto_serial,
            "label": info.label,
            "mac": info.mac,
            "unit_type": info.unit_type,
        }
        for serial, info in devices.items()
    }
    if cache != entry.data.get(CONF_DEVICES):
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_DEVICES: cache}
        )


def _merge_cached_into_devices(
    devices: dict[str, DeviceInfo], cached: dict[str, dict[str, Any]]
) -> None:
    """Fill in credentials that discovery did not return."""
    for serial, info in devices.items():
        if not (c := cached.get(serial)):
            continue
        if not info.address and c.get("address"):
            info.address = c["address"]
        if not info.password and c.get("password"):
            info.password = c["password"]
        if not info.crypto_serial and c.get("crypto_serial"):
            info.crypto_serial = c["crypto_serial"]


async def async_setup_entry(
    hass: HomeAssistant, entry: MitsubishiComfortConfigEntry
) -> bool:
    """Set up Mitsubishi Comfort from a config entry."""
    account = MitsubishiCloudAccount(
        entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
    )
    try:
        await account.login()
    except AuthenticationError as err:
        await account.close()
        raise ConfigEntryError(f"Authentication failed: {err}") from err
    except DeviceConnectionError as err:
        await account.close()
        raise ConfigEntryNotReady(
            f"Could not connect to Mitsubishi cloud: {err}"
        ) from err

    legacy_path = hass.config.path(LEGACY_CREDENTIAL_CACHE)
    migrate_legacy = CONF_DEVICES not in entry.data
    if not migrate_legacy:
        cached = entry.data[CONF_DEVICES]
    else:
        cached = await hass.async_add_executor_job(
            _load_legacy_credentials, legacy_path
        )

    # Cached passwords skip the Socket.IO fetch for those devices.
    try:
        devices = await account.discover_devices(
            cached_credentials=cached, cloud_fallback=True
        )
    except DeviceConnectionError as err:
        await account.close()
        raise ConfigEntryNotReady(f"Device discovery failed: {err}") from err
    if not devices:
        await account.close()
        raise ConfigEntryNotReady("No devices discovered")

    _merge_cached_into_devices(devices, cached)

    # The cloud API doesn't return LAN addresses; match DHCP leases instead.
    if missing_addr := {s: d for s, d in devices.items() if not d.address}:
        candidate_ips = [
            info.ip
            for info in async_discovered_service_info(hass)
            if info.macaddress.lower().startswith(DHCP_MAC_PREFIXES)
        ]
        if candidate_ips:
            matched = await probe_candidate_ips(
                missing_addr, candidate_ips, timeout=3.0
            )
            for serial, ip in matched.items():
                devices[serial].address = ip

    _save_credentials(hass, entry, devices)
    if migrate_legacy:
        await hass.async_add_executor_job(_remove_legacy_credentials, legacy_path)

    connect_timeout = entry.options.get(CONF_CONNECT_TIMEOUT, DEFAULT_CONNECT_TIMEOUT)
    response_timeout = entry.options.get(
        CONF_RESPONSE_TIMEOUT, DEFAULT_RESPONSE_TIMEOUT
    )

    coordinators: dict[str, MitsubishiComfortCoordinator] = {}
    retry_serials: list[str] = []
    for serial, info in devices.items():
        if _has_local_credentials(info):
            device = _make_device(info, serial, connect_timeout, response_timeout)
        elif info.site_id:
            _LOGGER.info("%s has no local credentials; using cloud control", info.label)
            device = CloudIndoorUnit(info, account)
            retry_serials.append(serial)
        else:
            _LOGGER.warning(
                "%s is missing credentials (address=%s, password=%s, crypto=%s);"
                " retrying in the background",
                info.label,
                bool(info.address),
                bool(info.password),
                bool(info.crypto_serial),
            )
            retry_serials.append(serial)
            continue
        coordinators[serial] = MitsubishiComfortCoordinator(hass, entry, device)

    if not coordinators:
        await account.close()
        raise ConfigEntryNotReady("No devices have usable credentials yet")

    # A missed first poll isn't fatal; coordinators fail after repeated misses.
    await asyncio.gather(
        *(c.async_config_entry_first_refresh() for c in coordinators.values())
    )

    entry.runtime_data = MitsubishiComfortData(coordinators, account)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # A background task, not a tracked one, so HA startup doesn't wait on the
    # retry's sleeps and long polls. It is cancelled when the entry unloads.
    if retry_serials:
        entry.async_create_background_task(
            hass,
            _retry_local_credentials(hass, entry, account, devices, retry_serials),
            f"{DOMAIN}_retry_local_credentials",
        )

    return True


async def _retry_local_credentials(
    hass: HomeAssistant,
    entry: MitsubishiComfortConfigEntry,
    account: MitsubishiCloudAccount,
    devices: dict[str, DeviceInfo],
    serials: list[str],
) -> None:
    """Fetch missing local credentials, then reload to switch devices to LAN."""
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        await asyncio.sleep(RETRY_DELAY * attempt)
        _LOGGER.debug(
            "Local credential retry %d/%d for %d devices",
            attempt,
            RETRY_ATTEMPTS,
            len(serials),
        )

        passwords = await account.get_passwords_via_websocket(serials, timeout_secs=60)
        for serial in serials:
            if serial in passwords and not devices[serial].password:
                devices[serial].password = passwords[serial]

        if any(_has_local_credentials(devices[s]) for s in serials):
            _save_credentials(hass, entry, devices)
            # Scheduled, not awaited: unloading the entry cancels this task.
            hass.config_entries.async_schedule_reload(entry.entry_id)
            return

    _LOGGER.info(
        "No local credentials for %s; staying on cloud control or unavailable",
        ", ".join(devices[s].label for s in serials),
    )


async def async_unload_entry(
    hass: HomeAssistant, entry: MitsubishiComfortConfigEntry
) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await asyncio.gather(
            *(c.device.close() for c in entry.runtime_data.coordinators.values())
        )
        await entry.runtime_data.account.close()
    return unload_ok
