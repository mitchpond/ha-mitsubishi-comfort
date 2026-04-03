"""Tests for the Mitsubishi Comfort sensor entities."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from homeassistant.components.mitsubishi_comfort.lib.types import DeviceStatus
from homeassistant.components.mitsubishi_comfort.sensor import (
    MitsubishiComfortHumiditySensor,
    MitsubishiComfortOutdoorTemperatureSensor,
    MitsubishiComfortSensorBatterySensor,
    MitsubishiComfortSensorSignalSensor,
    MitsubishiComfortTemperatureSensor,
    MitsubishiComfortUptimeSensor,
    MitsubishiComfortWifiSignalSensor,
)


def _make_sensor(cls, coordinator: MagicMock):
    """Create a sensor entity bypassing CoordinatorEntity init."""
    if cls in (
        MitsubishiComfortTemperatureSensor,
        MitsubishiComfortHumiditySensor,
        MitsubishiComfortWifiSignalSensor,
        MitsubishiComfortSensorBatterySensor,
        MitsubishiComfortSensorSignalSensor,
        MitsubishiComfortUptimeSensor,
        MitsubishiComfortOutdoorTemperatureSensor,
    ):
        entity = cls.__new__(cls)
        entity.coordinator = coordinator
        entity._device = coordinator.device
        # Determine suffix from class
        suffix_map = {
            MitsubishiComfortTemperatureSensor: "current-temperature",
            MitsubishiComfortHumiditySensor: "current-humidity",
            MitsubishiComfortWifiSignalSensor: "wifi-signal",
            MitsubishiComfortSensorBatterySensor: "sensor-battery",
            MitsubishiComfortSensorSignalSensor: "sensor-signal",
            MitsubishiComfortUptimeSensor: "uptime",
            MitsubishiComfortOutdoorTemperatureSensor: "outdoor-temperature",
        }
        suffix = suffix_map[cls]
        entity._attr_unique_id = f"{coordinator.device.serial}-{suffix}"
        entity._attr_name = f"{coordinator.device.name} {suffix.replace('-', ' ').title()}"
        entity.hass = None
        return entity


class TestTemperatureSensor:
    def test_value(self, mock_coordinator):
        sensor = _make_sensor(MitsubishiComfortTemperatureSensor, mock_coordinator)
        assert sensor.native_value == 23.5

    def test_enabled_by_default(self):
        assert MitsubishiComfortTemperatureSensor._attr_entity_registry_enabled_default is True


class TestHumiditySensor:
    def test_value(self, mock_coordinator):
        sensor = _make_sensor(MitsubishiComfortHumiditySensor, mock_coordinator)
        assert sensor.native_value == 45.0

    def test_disabled_by_default(self):
        assert MitsubishiComfortHumiditySensor._attr_entity_registry_enabled_default is False


class TestWifiSignalSensor:
    def test_value(self, mock_coordinator):
        sensor = _make_sensor(MitsubishiComfortWifiSignalSensor, mock_coordinator)
        assert sensor.native_value == -55

    def test_disabled_by_default(self):
        assert MitsubishiComfortWifiSignalSensor._attr_entity_registry_enabled_default is False


class TestSensorBatterySensor:
    def test_value(self, mock_coordinator):
        sensor = _make_sensor(MitsubishiComfortSensorBatterySensor, mock_coordinator)
        assert sensor.native_value == 80

    def test_disabled_by_default(self):
        assert MitsubishiComfortSensorBatterySensor._attr_entity_registry_enabled_default is False


class TestSensorSignalSensor:
    def test_value(self, mock_coordinator):
        sensor = _make_sensor(MitsubishiComfortSensorSignalSensor, mock_coordinator)
        assert sensor.native_value == -60

    def test_disabled_by_default(self):
        assert MitsubishiComfortSensorSignalSensor._attr_entity_registry_enabled_default is False


class TestUptimeSensor:
    def test_value(self, mock_coordinator):
        sensor = _make_sensor(MitsubishiComfortUptimeSensor, mock_coordinator)
        assert sensor.native_value == 86400

    def test_disabled_by_default(self):
        assert MitsubishiComfortUptimeSensor._attr_entity_registry_enabled_default is False


class TestOutdoorTemperatureSensor:
    def test_value(self, mock_coordinator):
        mock_coordinator.device.status.outdoor_temperature = 32.0
        sensor = _make_sensor(
            MitsubishiComfortOutdoorTemperatureSensor, mock_coordinator
        )
        assert sensor.native_value == 32.0

    def test_disabled_by_default(self):
        assert (
            MitsubishiComfortOutdoorTemperatureSensor._attr_entity_registry_enabled_default
            is False
        )


class TestSensorNoneValue:
    def test_temperature_none(self, mock_coordinator):
        mock_coordinator.device.status.room_temperature = None
        sensor = _make_sensor(MitsubishiComfortTemperatureSensor, mock_coordinator)
        assert sensor.native_value is None

    def test_humidity_none(self, mock_coordinator):
        mock_coordinator.device.status.current_humidity = None
        sensor = _make_sensor(MitsubishiComfortHumiditySensor, mock_coordinator)
        assert sensor.native_value is None

    def test_wifi_none(self, mock_coordinator):
        mock_coordinator.device.status.wifi_rssi = None
        sensor = _make_sensor(MitsubishiComfortWifiSignalSensor, mock_coordinator)
        assert sensor.native_value is None


class TestSensorDeviceInfo:
    def test_device_info(self, mock_coordinator):
        sensor = _make_sensor(MitsubishiComfortTemperatureSensor, mock_coordinator)
        info = sensor.device_info
        assert ("mitsubishi_comfort", "SERIAL001") in info["identifiers"]
        assert info["name"] == "Living Room"
        assert info["manufacturer"] == "Mitsubishi"
