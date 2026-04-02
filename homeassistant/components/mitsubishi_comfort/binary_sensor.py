"""Binary sensor entities for Mitsubishi Comfort integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .lib import IndoorUnit
from .const import DOMAIN
from .coordinator import MitsubishiComfortCoordinator
from .entity import MitsubishiComfortEntity


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


class MitsubishiComfortFilterDirtySensor(MitsubishiComfortEntity, BinarySensorEntity):
    """Filter dirty binary sensor — on means filter needs cleaning."""

    def __init__(self, coordinator: MitsubishiComfortCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._device.serial}-filter-dirty"
        self._attr_name = f"{self._device.name} Filter Dirty"

    @property
    def is_on(self) -> bool | None:
        return self._device.status.filter_dirty
