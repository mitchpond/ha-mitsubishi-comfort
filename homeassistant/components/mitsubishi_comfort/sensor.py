"""Sensor entities for Mitsubishi Comfort integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS, UnitOfTemperature
from homeassistant.helpers.entity import EntityCategory

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .lib import CloudIndoorUnit, IndoorUnit, KumoStation

from .const import DOMAIN
from .coordinator import MitsubishiComfortCoordinator
from .entity import MitsubishiComfortEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Mitsubishi Comfort sensor entities."""
    coordinators = hass.data[DOMAIN][entry.entry_id]["coordinators"]
    entities = []
    for coordinator in coordinators.values():
        # Local-only sensors (LAN adapter data)
        if isinstance(coordinator.device, (IndoorUnit, KumoStation)):
            entities.append(MitsubishiComfortWifiSignalSensor(coordinator))
            entities.append(MitsubishiComfortUptimeSensor(coordinator))
        # Indoor unit sensors (local or cloud)
        if isinstance(coordinator.device, (IndoorUnit, CloudIndoorUnit)):
            entities.append(MitsubishiComfortTemperatureSensor(coordinator))
            entities.append(MitsubishiComfortHumiditySensor(coordinator))
        # Local indoor unit-only sensors (require LAN adapter)
        if isinstance(coordinator.device, IndoorUnit):
            entities.append(MitsubishiComfortSensorBatterySensor(coordinator))
            entities.append(MitsubishiComfortSensorSignalSensor(coordinator))
        # KumoStation sensors
        if isinstance(coordinator.device, KumoStation):
            entities.append(MitsubishiComfortOutdoorTemperatureSensor(coordinator))
    async_add_entities(entities)


class MitsubishiComfortSensorBase(MitsubishiComfortEntity, SensorEntity):
    """Base class for Mitsubishi Comfort sensors."""

    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: MitsubishiComfortCoordinator, suffix: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._device.serial}-{suffix}"
        self._attr_name = f"{self._device.name} {suffix.replace('-', ' ').title()}"


class MitsubishiComfortTemperatureSensor(MitsubishiComfortSensorBase):
    """Current temperature sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator: MitsubishiComfortCoordinator) -> None:
        super().__init__(coordinator, "current-temperature")

    @property
    def native_value(self) -> float | None:
        return self._device.status.room_temperature


class MitsubishiComfortHumiditySensor(MitsubishiComfortSensorBase):
    """Current humidity sensor."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: MitsubishiComfortCoordinator) -> None:
        super().__init__(coordinator, "current-humidity")

    @property
    def native_value(self) -> float | None:
        return self._device.status.current_humidity


class MitsubishiComfortWifiSignalSensor(MitsubishiComfortSensorBase):
    """WiFi signal strength sensor."""

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS

    def __init__(self, coordinator: MitsubishiComfortCoordinator) -> None:
        super().__init__(coordinator, "wifi-signal")

    @property
    def native_value(self) -> int | None:
        return self._device.status.wifi_rssi


class MitsubishiComfortSensorBatterySensor(MitsubishiComfortSensorBase):
    """External sensor battery level."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: MitsubishiComfortCoordinator) -> None:
        super().__init__(coordinator, "sensor-battery")

    @property
    def native_value(self) -> int | None:
        return self._device.status.sensor_battery


class MitsubishiComfortSensorSignalSensor(MitsubishiComfortSensorBase):
    """External sensor signal strength."""

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS

    def __init__(self, coordinator: MitsubishiComfortCoordinator) -> None:
        super().__init__(coordinator, "sensor-signal")

    @property
    def native_value(self) -> int | None:
        return self._device.status.sensor_rssi


class MitsubishiComfortOutdoorTemperatureSensor(MitsubishiComfortSensorBase):
    """Outdoor temperature sensor (KumoStation only)."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: MitsubishiComfortCoordinator) -> None:
        super().__init__(coordinator, "outdoor-temperature")

    @property
    def native_value(self) -> float | None:
        return self._device.status.outdoor_temperature


class MitsubishiComfortUptimeSensor(MitsubishiComfortSensorBase):
    """Device uptime sensor."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = "s"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: MitsubishiComfortCoordinator) -> None:
        super().__init__(coordinator, "uptime")

    @property
    def native_value(self) -> int | None:
        return self._device.status.uptime
