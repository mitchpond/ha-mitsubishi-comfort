"""Tests for the Mitsubishi Comfort integration."""

from enum import Enum
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from mitsubishi_comfort import KumoStation
from mitsubishi_comfort.types import (
    CommandResult,
    DeviceInfo,
    DeviceStatus,
    FanSpeed,
    Mode,
    VaneDirection,
)

LOCAL_SERIAL = "SER001"
CLOUD_SERIAL = "SER002"
STATION_SERIAL = "SER003"


def make_device_info(serial: str, **kwargs: Any) -> DeviceInfo:
    """Return discovery info for a device with full local credentials."""
    fields = {
        "label": {
            LOCAL_SERIAL: "Living Room",
            CLOUD_SERIAL: "Bedroom",
            STATION_SERIAL: "Outdoor",
        }.get(serial, serial),
        "address": "192.0.2.10",
        "mac": "24cd8d000001",
        "unit_type": "headless" if serial == STATION_SERIAL else "ductless",
        "password": "cGFzc3dvcmQ=",
        "crypto_serial": "0102030405060708090a",
        "site_id": "site1",
    }
    return DeviceInfo(serial=serial, **(fields | kwargs))


def default_discovery() -> dict[str, DeviceInfo]:
    """Return a local unit, a cloud-only unit and a Kumo Station."""
    return {
        LOCAL_SERIAL: make_device_info(LOCAL_SERIAL),
        CLOUD_SERIAL: make_device_info(
            CLOUD_SERIAL, address="", password="", crypto_serial=""
        ),
        STATION_SERIAL: make_device_info(STATION_SERIAL),
    }


def _accept(value: Any) -> CommandResult:
    return CommandResult(
        success=True, value=value.value if isinstance(value, Enum) else value
    )


def make_device(cls: type, serial: str, name: str) -> MagicMock:
    """Return a mock device that passes isinstance checks for cls."""
    device = MagicMock(spec=cls)
    device.serial = serial
    device.name = name
    device.update_status = AsyncMock(return_value=True)
    device.close = AsyncMock()
    if cls is KumoStation:
        device.status = DeviceStatus(
            outdoor_temperature=8.5, wifi_rssi=-55, uptime=3600
        )
        return device
    device.status = DeviceStatus(
        mode="cool",
        standby=False,
        cool_setpoint=24.0,
        heat_setpoint=20.0,
        room_temperature=25.5,
        current_humidity=45.0,
        fan_speed="auto",
        vane_direction="auto",
        vane_left_right="center",
        filter_dirty=False,
        wifi_rssi=-60,
        sensor_battery=90,
        sensor_rssi=-70,
        uptime=7200,
        firmware_version="1.0",
        min_cool_setpoint=16.0,
        max_cool_setpoint=31.0,
        min_heat_setpoint=10.0,
        max_heat_setpoint=31.0,
    )
    device.supported_modes = list(Mode)
    device.supported_fan_speeds = [FanSpeed.AUTO, FanSpeed.LOW, FanSpeed.POWERFUL]
    device.supported_vane_directions = [VaneDirection.AUTO, VaneDirection.SWING]
    for command in (
        "set_mode",
        "set_cool_setpoint",
        "set_heat_setpoint",
        "set_fan_speed",
        "set_vane_direction",
    ):
        setattr(device, command, AsyncMock(side_effect=_accept))
    return device
