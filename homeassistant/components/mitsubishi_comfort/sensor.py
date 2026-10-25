"""Sensor entities for Mitsubishi Comfort integration."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from mitsubishi_comfort import CloudIndoorUnit, IndoorUnit, KumoStation
from mitsubishi_comfort.types import DeviceStatus

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS,
    EntityCategory,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import (
    MitsubishiComfortConfigEntry,
    MitsubishiComfortCoordinator,
    MitsubishiComfortDevice,
)
from .entity import MitsubishiComfortEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class MitsubishiComfortSensorEntityDescription(SensorEntityDescription):
    """Describes a Mitsubishi Comfort sensor."""

    value_fn: Callable[[DeviceStatus], float | int | None]
    device_types: tuple[type[MitsubishiComfortDevice], ...]


# Signal, uptime and external-sensor data come from the LAN adapter, so
# cloud-controlled units only get temperature and humidity.
SENSORS: tuple[MitsubishiComfortSensorEntityDescription, ...] = (
    MitsubishiComfortSensorEntityDescription(
        key="current-temperature",
        translation_key="current_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda status: status.room_temperature,
        device_types=(IndoorUnit, CloudIndoorUnit),
    ),
    MitsubishiComfortSensorEntityDescription(
        key="current-humidity",
        translation_key="current_humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        entity_registry_enabled_default=False,
        value_fn=lambda status: status.current_humidity,
        device_types=(IndoorUnit, CloudIndoorUnit),
    ),
    MitsubishiComfortSensorEntityDescription(
        key="wifi-signal",
        translation_key="wifi_signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda status: status.wifi_rssi,
        device_types=(IndoorUnit, KumoStation),
    ),
    MitsubishiComfortSensorEntityDescription(
        key="sensor-battery",
        translation_key="sensor_battery",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda status: status.sensor_battery,
        device_types=(IndoorUnit,),
    ),
    MitsubishiComfortSensorEntityDescription(
        key="sensor-signal",
        translation_key="sensor_signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda status: status.sensor_rssi,
        device_types=(IndoorUnit,),
    ),
    MitsubishiComfortSensorEntityDescription(
        key="outdoor-temperature",
        translation_key="outdoor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_registry_enabled_default=False,
        value_fn=lambda status: status.outdoor_temperature,
        device_types=(KumoStation,),
    ),
    MitsubishiComfortSensorEntityDescription(
        key="uptime",
        translation_key="uptime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda status: status.uptime,
        device_types=(IndoorUnit, KumoStation),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MitsubishiComfortConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Mitsubishi Comfort sensor entities."""
    async_add_entities(
        MitsubishiComfortSensor(coordinator, description)
        for coordinator in entry.runtime_data.coordinators.values()
        for description in SENSORS
        if isinstance(coordinator.device, description.device_types)
    )


class MitsubishiComfortSensor(MitsubishiComfortEntity, SensorEntity):
    """Sensor for a Mitsubishi Comfort device."""

    entity_description: MitsubishiComfortSensorEntityDescription

    def __init__(
        self,
        coordinator: MitsubishiComfortCoordinator,
        description: MitsubishiComfortSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._device.serial}-{description.key}"

    @property
    @override
    def native_value(self) -> float | int | None:
        """Return the sensor value."""
        return self.entity_description.value_fn(self._device.status)
