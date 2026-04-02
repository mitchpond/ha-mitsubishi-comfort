"""Binary sensor entities for Mitsubishi Comfort integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .lib import IndoorUnit
from .const import DOMAIN
from .coordinator import MitsubishiComfortCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Mitsubishi Comfort binary sensor entities."""
    coordinators = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for coordinator in coordinators.values():
        if isinstance(coordinator.device, IndoorUnit):
            entities.append(MitsubishiComfortFilterDirtySensor(coordinator))
    async_add_entities(entities)


class MitsubishiComfortFilterDirtySensor(CoordinatorEntity[MitsubishiComfortCoordinator], BinarySensorEntity):
    """Filter dirty binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: MitsubishiComfortCoordinator) -> None:
        super().__init__(coordinator)
        self._device = coordinator.device
        self._attr_unique_id = f"{self._device.serial}-filter-dirty"
        self._attr_name = f"{self._device.name} Filter"

    @property
    def is_on(self) -> bool | None:
        return self._device.status.filter_dirty

    @property
    def available(self) -> bool:
        return self.coordinator.available

    @property
    def device_info(self):
        info = {
            "identifiers": {("mitsubishi_comfort", self._device.serial)},
            "name": self._device.name,
            "manufacturer": "Mitsubishi",
        }
        if self._device.status.firmware_version:
            info["sw_version"] = self._device.status.firmware_version
        if self._device.status.hardware_version:
            info["hw_version"] = self._device.status.hardware_version
        return info
