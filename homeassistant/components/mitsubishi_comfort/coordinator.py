"""DataUpdateCoordinator for Mitsubishi Comfort devices."""

from dataclasses import dataclass
import logging
from typing import override

from mitsubishi_comfort import (
    CloudIndoorUnit,
    IndoorUnit,
    KumoStation,
    MitsubishiCloudAccount,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

MAX_FAILURES_BEFORE_UNAVAILABLE = 3

type MitsubishiComfortDevice = IndoorUnit | KumoStation | CloudIndoorUnit
type MitsubishiComfortConfigEntry = ConfigEntry[MitsubishiComfortData]


class MitsubishiComfortCoordinator(DataUpdateCoordinator[None]):
    """Coordinator to poll a single Mitsubishi device."""

    config_entry: MitsubishiComfortConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: MitsubishiComfortConfigEntry,
        device: MitsubishiComfortDevice,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN}_{device.serial}",
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.device = device
        self._consecutive_failures = 0

    @override
    async def _async_update_data(self) -> None:
        """Poll the device, tolerating a few missed polls before failing."""
        if await self.device.update_status():
            self._consecutive_failures = 0
            return
        self._consecutive_failures += 1
        _LOGGER.debug(
            "Poll of %s failed (%d consecutive)",
            self.device.name,
            self._consecutive_failures,
        )
        if self._consecutive_failures >= MAX_FAILURES_BEFORE_UNAVAILABLE:
            raise UpdateFailed(
                f"{self.device.name} did not respond to "
                f"{self._consecutive_failures} consecutive polls"
            )


@dataclass
class MitsubishiComfortData:
    """Runtime data for a config entry."""

    coordinators: dict[str, MitsubishiComfortCoordinator]
    account: MitsubishiCloudAccount
