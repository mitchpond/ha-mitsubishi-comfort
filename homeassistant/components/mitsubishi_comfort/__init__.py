"""Mitsubishi Comfort integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from mitsubishi_comfort import IndoorUnit, KumoStation, MitsubishiCloudAccount

from .const import CONF_CONNECT_TIMEOUT, CONF_RESPONSE_TIMEOUT, DOMAIN, PLATFORMS
from .coordinator import MitsubishiComfortCoordinator

_LOGGER = logging.getLogger(__name__)

type MitsubishiComfortConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: MitsubishiComfortConfigEntry) -> bool:
    """Set up Mitsubishi Comfort from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    account = MitsubishiCloudAccount(username, password)
    if not await account.login():
        raise ConfigEntryNotReady("Failed to authenticate with Mitsubishi cloud")

    devices = await account.discover_devices()
    if not devices:
        raise ConfigEntryNotReady("No devices discovered")

    connect_timeout = float(entry.options.get(CONF_CONNECT_TIMEOUT, 1.2))
    response_timeout = float(entry.options.get(CONF_RESPONSE_TIMEOUT, 8.0))

    coordinators: dict[str, MitsubishiComfortCoordinator] = {}
    for serial, info in devices.items():
        if info.is_indoor_unit:
            device = IndoorUnit(
                name=info.label,
                address=info.address,
                password_b64=info.password,
                crypto_serial_hex=info.crypto_serial,
                serial=serial,
                connect_timeout=connect_timeout,
                response_timeout=response_timeout,
            )
        else:
            device = KumoStation(
                name=info.label,
                address=info.address,
                password_b64=info.password,
                crypto_serial_hex=info.crypto_serial,
                serial=serial,
                connect_timeout=connect_timeout,
                response_timeout=response_timeout,
            )
        coordinators[serial] = MitsubishiComfortCoordinator(hass, device)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinators

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MitsubishiComfortConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
