"""Base entity for Mitsubishi Comfort integration."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MitsubishiComfortCoordinator


class MitsubishiComfortEntity(CoordinatorEntity[MitsubishiComfortCoordinator]):
    """Base class for all Mitsubishi Comfort entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MitsubishiComfortCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._device = coordinator.device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device.serial)},
            name=self._device.name,
            manufacturer="Mitsubishi",
            serial_number=self._device.serial,
            sw_version=self._device.status.firmware_version,
            hw_version=self._device.status.hardware_version,
        )
