"""Shared fixtures for Mitsubishi Comfort tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from homeassistant.components.mitsubishi_comfort.lib.types import (
    CommandResult,
    DeviceInfo,
    DeviceStatus,
    FanSpeed,
    Mode,
    VaneDirection,
)


@pytest.fixture
def mock_device_status() -> DeviceStatus:
    """Return a realistic DeviceStatus."""
    return DeviceStatus(
        mode="cool",
        standby=False,
        heat_setpoint=21.0,
        cool_setpoint=24.0,
        room_temperature=23.5,
        fan_speed="auto",
        vane_direction="auto",
        filter_dirty=False,
        defrost=False,
        current_humidity=45.0,
        outdoor_temperature=30.0,
        wifi_rssi=-55,
        sensor_battery=80,
        sensor_rssi=-60,
        run_state="on",
        vane_left_right="auto",
        uptime=86400,
        firmware_version="2.1.0",
        hardware_version="1.0.0",
        min_cool_setpoint=18.0,
        max_cool_setpoint=30.0,
        min_heat_setpoint=16.0,
        max_heat_setpoint=28.0,
    )


@pytest.fixture
def mock_indoor_unit(mock_device_status: DeviceStatus) -> MagicMock:
    """Return a MagicMock of IndoorUnit with realistic attributes."""
    unit = MagicMock()
    unit.name = "Living Room"
    unit.serial = "SERIAL001"
    unit.address = "192.168.1.100"
    type(unit).status = PropertyMock(return_value=mock_device_status)
    unit.supported_modes = [Mode.OFF, Mode.COOL, Mode.HEAT, Mode.DRY, Mode.FAN, Mode.AUTO]
    unit.supported_fan_speeds = [
        FanSpeed.SUPER_QUIET,
        FanSpeed.QUIET,
        FanSpeed.LOW,
        FanSpeed.POWERFUL,
        FanSpeed.SUPER_POWERFUL,
        FanSpeed.AUTO,
    ]
    unit.supported_vane_directions = [
        VaneDirection.HORIZONTAL,
        VaneDirection.MID_HORIZONTAL,
        VaneDirection.MIDPOINT,
        VaneDirection.MID_VERTICAL,
        VaneDirection.VERTICAL,
        VaneDirection.AUTO,
        VaneDirection.SWING,
    ]
    unit.set_mode = AsyncMock(return_value=CommandResult(success=True, value="cool"))
    unit.set_cool_setpoint = AsyncMock(return_value=CommandResult(success=True, value=24.0))
    unit.set_heat_setpoint = AsyncMock(return_value=CommandResult(success=True, value=21.0))
    unit.set_fan_speed = AsyncMock(return_value=CommandResult(success=True, value="auto"))
    unit.set_vane_direction = AsyncMock(return_value=CommandResult(success=True, value="auto"))
    unit.update_status = AsyncMock(return_value=True)
    unit.close = AsyncMock()
    return unit


@pytest.fixture
def mock_kumo_station() -> MagicMock:
    """Return a MagicMock of KumoStation."""
    station = MagicMock()
    station.name = "Outdoor Unit"
    station.serial = "KUMO001"
    station.address = "192.168.1.101"
    station.status = DeviceStatus(
        outdoor_temperature=32.0,
        wifi_rssi=-50,
        sensor_rssi=-65,
    )
    station.update_status = AsyncMock(return_value=True)
    station.close = AsyncMock()
    return station


@pytest.fixture
def mock_coordinator(mock_indoor_unit: MagicMock) -> MagicMock:
    """Return a MagicMock of MitsubishiComfortCoordinator."""
    coordinator = MagicMock()
    coordinator.device = mock_indoor_unit
    coordinator.available = True
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


@pytest.fixture
def mock_cloud_account() -> AsyncMock:
    """Return an AsyncMock of MitsubishiCloudAccount."""
    account = AsyncMock()
    account.login = AsyncMock(return_value=True)
    account.discover_devices = AsyncMock(return_value={
        "SERIAL001": DeviceInfo(
            serial="SERIAL001",
            label="Living Room",
            address="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            unit_type="ductless",
            password="dGVzdHBhc3M=",
            crypto_serial="0102030405060708090a",
        ),
    })
    account.get_sites = AsyncMock(return_value=[{"id": "site1", "name": "Home"}])
    account.get_zones = AsyncMock(return_value=[])
    account.refresh = AsyncMock(return_value=True)
    account.close = AsyncMock()
    return account


@pytest.fixture
def mock_device_info() -> DeviceInfo:
    """Return a real DeviceInfo instance."""
    return DeviceInfo(
        serial="SERIAL001",
        label="Living Room",
        address="192.168.1.100",
        mac="AA:BB:CC:DD:EE:FF",
        unit_type="ductless",
        password="dGVzdHBhc3M=",
        crypto_serial="0102030405060708090a",
    )
