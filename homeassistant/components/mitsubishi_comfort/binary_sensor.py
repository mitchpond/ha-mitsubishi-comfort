"""Binary sensor entities for Mitsubishi Comfort integration."""

from typing import override

from mitsubishi_comfort import IndoorUnit

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MitsubishiComfortConfigEntry, MitsubishiComfortCoordinator
from .entity import MitsubishiComfortEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MitsubishiComfortConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Mitsubishi Comfort binary sensor entities."""
    async_add_entities(
        MitsubishiComfortFilterDirtySensor(coordinator)
        for coordinator in entry.runtime_data.coordinators.values()
        if isinstance(coordinator.device, IndoorUnit)
    )


class MitsubishiComfortFilterDirtySensor(MitsubishiComfortEntity, BinarySensorEntity):
    """Binary sensor that is on when the filter needs cleaning."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "filter_dirty"

    def __init__(self, coordinator: MitsubishiComfortCoordinator) -> None:
        """Initialize the filter sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._device.serial}-filter-dirty"

    @property
    @override
    def is_on(self) -> bool | None:
        """Return whether the filter needs cleaning."""
        return self._device.status.filter_dirty
