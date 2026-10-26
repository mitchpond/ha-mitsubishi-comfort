"""Tests for the Mitsubishi Comfort climate entity."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)

from homeassistant.components.mitsubishi_comfort.climate import (
    MitsubishiComfortClimate,
    _MODE_TO_ACTION,
    _MODE_TO_HVAC,
)
from homeassistant.components.mitsubishi_comfort.lib.types import (
    CommandResult,
    DeviceStatus,
    FanSpeed,
    Mode,
    VaneDirection,
)


def _make_climate(coordinator: MagicMock) -> MitsubishiComfortClimate:
    """Create a climate entity from a mock coordinator, bypassing CoordinatorEntity init."""
    entity = MitsubishiComfortClimate.__new__(MitsubishiComfortClimate)
    entity.coordinator = coordinator
    entity._device = coordinator.device
    entity._attr_name = coordinator.device.name
    entity._attr_unique_id = coordinator.device.serial
    entity._optimistic_mode = None
    entity._optimistic_cool_setpoint = None
    entity._optimistic_heat_setpoint = None
    entity._optimistic_fan_speed = None
    entity._optimistic_vane_direction = None
    entity.hass = None
    return entity


# ── HVAC mode mappings ──


class TestHVACModeMappings:
    def test_off(self):
        assert _MODE_TO_HVAC["off"] == HVACMode.OFF

    def test_cool(self):
        assert _MODE_TO_HVAC["cool"] == HVACMode.COOL

    def test_heat(self):
        assert _MODE_TO_HVAC["heat"] == HVACMode.HEAT

    def test_dry(self):
        assert _MODE_TO_HVAC["dry"] == HVACMode.DRY

    def test_vent(self):
        assert _MODE_TO_HVAC["vent"] == HVACMode.FAN_ONLY

    def test_auto(self):
        assert _MODE_TO_HVAC["auto"] == HVACMode.HEAT_COOL

    def test_auto_cool(self):
        assert _MODE_TO_HVAC["autoCool"] == HVACMode.HEAT_COOL

    def test_auto_heat(self):
        assert _MODE_TO_HVAC["autoHeat"] == HVACMode.HEAT_COOL


# ── HVAC action mappings ──


class TestHVACActionMappings:
    def test_off(self):
        assert _MODE_TO_ACTION["off"] == HVACAction.OFF

    def test_cool(self):
        assert _MODE_TO_ACTION["cool"] == HVACAction.COOLING

    def test_heat(self):
        assert _MODE_TO_ACTION["heat"] == HVACAction.HEATING

    def test_dry(self):
        assert _MODE_TO_ACTION["dry"] == HVACAction.DRYING

    def test_vent(self):
        assert _MODE_TO_ACTION["vent"] == HVACAction.FAN

    def test_auto_idle(self):
        assert _MODE_TO_ACTION["auto"] == HVACAction.IDLE

    def test_auto_cool_active(self):
        assert _MODE_TO_ACTION["autoCool"] == HVACAction.COOLING

    def test_auto_heat_active(self):
        assert _MODE_TO_ACTION["autoHeat"] == HVACAction.HEATING

    def test_standby_returns_idle(self, mock_coordinator):
        """When standby is True, hvac_action should be IDLE regardless of mode."""
        mock_coordinator.device.status.standby = True
        mock_coordinator.device.status.mode = "cool"
        entity = _make_climate(mock_coordinator)
        assert entity.hvac_action == HVACAction.IDLE


# ── Target temperature ──


class TestTargetTemperature:
    def test_target_temperature_cool_mode(self, mock_coordinator):
        mock_coordinator.device.status.mode = "cool"
        mock_coordinator.device.status.cool_setpoint = 24.0
        entity = _make_climate(mock_coordinator)
        assert entity.target_temperature == 24.0

    def test_target_temperature_heat_mode(self, mock_coordinator):
        mock_coordinator.device.status.mode = "heat"
        mock_coordinator.device.status.heat_setpoint = 21.0
        entity = _make_climate(mock_coordinator)
        assert entity.target_temperature == 21.0

    def test_target_temperature_auto_mode_returns_none(self, mock_coordinator):
        """In 'auto' mode, target_temperature returns None (uses range instead)."""
        mock_coordinator.device.status.mode = "auto"
        entity = _make_climate(mock_coordinator)
        assert entity.target_temperature is None

    @pytest.mark.parametrize("mode", ["autoCool", "autoHeat"])
    def test_target_temperature_auto_stage_returns_none(self, mock_coordinator, mode):
        """While auto is cooling or heating, only the range is exposed."""
        mock_coordinator.device.status.mode = mode
        mock_coordinator.device.status.cool_setpoint = 25.0
        mock_coordinator.device.status.heat_setpoint = 20.0
        entity = _make_climate(mock_coordinator)
        assert entity.hvac_mode == HVACMode.HEAT_COOL
        assert entity.target_temperature is None
        assert entity.target_temperature_high == 25.0
        assert entity.target_temperature_low == 20.0

    def test_target_temperature_high_low_auto(self, mock_coordinator):
        """In auto mode, high/low return cool/heat setpoints."""
        mock_coordinator.device.status.mode = "auto"
        mock_coordinator.device.status.cool_setpoint = 25.0
        mock_coordinator.device.status.heat_setpoint = 20.0
        entity = _make_climate(mock_coordinator)
        assert entity.target_temperature_high == 25.0
        assert entity.target_temperature_low == 20.0

    def test_target_temperature_high_low_non_auto(self, mock_coordinator):
        """In non-auto mode, high/low return None."""
        mock_coordinator.device.status.mode = "cool"
        entity = _make_climate(mock_coordinator)
        assert entity.target_temperature_high is None
        assert entity.target_temperature_low is None


# ── Optimistic state ──


class TestOptimisticState:
    async def test_optimistic_set_temperature_success(self, mock_coordinator):
        """After a successful set_cool_setpoint, cached state updates."""
        mock_coordinator.device.status.mode = "cool"
        mock_coordinator.device.set_cool_setpoint = AsyncMock(
            return_value=CommandResult(success=True, value=22.0)
        )
        entity = _make_climate(mock_coordinator)
        entity.async_write_ha_state = MagicMock()

        await entity.async_set_temperature(temperature=22.0)
        assert entity._optimistic_cool_setpoint == 22.0
        assert entity.target_temperature == 22.0
        entity.async_write_ha_state.assert_called_once()

    async def test_optimistic_set_temperature_heat(self, mock_coordinator):
        """In heat mode, a single temperature sets the heat setpoint."""
        mock_coordinator.device.status.mode = "heat"
        mock_coordinator.device.set_heat_setpoint = AsyncMock(
            return_value=CommandResult(success=True, value=19.5)
        )
        entity = _make_climate(mock_coordinator)
        entity.async_write_ha_state = MagicMock()

        await entity.async_set_temperature(temperature=19.5)
        mock_coordinator.device.set_heat_setpoint.assert_awaited_once_with(19.5)
        assert entity.target_temperature == 19.5
        assert entity.target_temperature_low is None

    async def test_optimistic_set_temperature_failure(self, mock_coordinator):
        """After a failed command, no optimistic state change."""
        mock_coordinator.device.status.mode = "cool"
        mock_coordinator.device.set_cool_setpoint = AsyncMock(
            return_value=CommandResult(success=False)
        )
        entity = _make_climate(mock_coordinator)
        entity.async_write_ha_state = MagicMock()

        await entity.async_set_temperature(temperature=22.0)
        assert entity._optimistic_cool_setpoint is None
        assert entity.target_temperature == 24.0  # original value
        entity.async_write_ha_state.assert_not_called()

    def test_optimistic_state_cleared_on_coordinator_update(self, mock_coordinator):
        """_handle_coordinator_update clears all optimistic state."""
        entity = _make_climate(mock_coordinator)
        entity._optimistic_mode = "heat"
        entity._optimistic_cool_setpoint = 22.0
        entity._optimistic_heat_setpoint = 20.0
        entity._optimistic_fan_speed = "quiet"
        entity._optimistic_vane_direction = "horizontal"
        entity.async_write_ha_state = MagicMock()

        entity._handle_coordinator_update()
        assert entity._optimistic_mode is None
        assert entity._optimistic_cool_setpoint is None
        assert entity._optimistic_heat_setpoint is None
        assert entity._optimistic_fan_speed is None
        assert entity._optimistic_vane_direction is None

    def test_optimistic_is_not_none_check(self, mock_coordinator):
        """Test that 0.0 setpoint works (not treated as falsy)."""
        mock_coordinator.device.status.mode = "cool"
        entity = _make_climate(mock_coordinator)
        entity._optimistic_cool_setpoint = 0.0
        # 0.0 is not None, so it should be returned
        assert entity.target_temperature == 0.0

    async def test_optimistic_auto_mode_exposes_range(self, mock_coordinator):
        """Switching to heat/cool shows both setpoints and no single setpoint."""
        mock_coordinator.device.status.mode = "cool"
        mock_coordinator.device.set_mode = AsyncMock(
            return_value=CommandResult(success=True, value="auto")
        )
        entity = _make_climate(mock_coordinator)
        entity.async_write_ha_state = MagicMock()

        await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
        assert entity.hvac_mode == HVACMode.HEAT_COOL
        assert entity.target_temperature is None
        assert entity.target_temperature_high == 24.0
        assert entity.target_temperature_low == 21.0

    @pytest.mark.parametrize("mode", ["auto", "autoCool", "autoHeat"])
    async def test_optimistic_range_in_auto(self, mock_coordinator, mode):
        """Setting the range in any auto variant updates both setpoints."""
        mock_coordinator.device.status.mode = mode
        mock_coordinator.device.set_cool_setpoint = AsyncMock(
            return_value=CommandResult(success=True, value=26.0)
        )
        mock_coordinator.device.set_heat_setpoint = AsyncMock(
            return_value=CommandResult(success=True, value=19.0)
        )
        entity = _make_climate(mock_coordinator)
        entity.async_write_ha_state = MagicMock()

        await entity.async_set_temperature(target_temp_low=19.0, target_temp_high=26.0)
        mock_coordinator.device.set_cool_setpoint.assert_awaited_once_with(26.0)
        mock_coordinator.device.set_heat_setpoint.assert_awaited_once_with(19.0)
        assert entity.target_temperature is None
        assert entity.target_temperature_high == 26.0
        assert entity.target_temperature_low == 19.0
        entity.async_write_ha_state.assert_called_once()

    @pytest.mark.parametrize(
        ("mode", "command", "other"),
        [
            ("autoCool", "set_cool_setpoint", "set_heat_setpoint"),
            ("autoHeat", "set_heat_setpoint", "set_cool_setpoint"),
        ],
    )
    async def test_single_setpoint_in_auto_stage(
        self, mock_coordinator, mode, command, other
    ):
        """A single temperature in an auto stage sets that stage's setpoint."""
        mock_coordinator.device.status.mode = mode
        setattr(
            mock_coordinator.device,
            command,
            AsyncMock(return_value=CommandResult(success=True, value=22.0)),
        )
        setattr(mock_coordinator.device, other, AsyncMock())
        entity = _make_climate(mock_coordinator)
        entity.async_write_ha_state = MagicMock()

        await entity.async_set_temperature(temperature=22.0)
        getattr(mock_coordinator.device, command).assert_awaited_once_with(22.0)
        getattr(mock_coordinator.device, other).assert_not_awaited()
        assert entity.target_temperature is None
        entity.async_write_ha_state.assert_called_once()


# ── Commands ──


class TestCommands:
    async def test_set_hvac_mode(self, mock_coordinator):
        mock_coordinator.device.set_mode = AsyncMock(
            return_value=CommandResult(success=True, value="heat")
        )
        entity = _make_climate(mock_coordinator)
        entity.async_write_ha_state = MagicMock()

        await entity.async_set_hvac_mode(HVACMode.HEAT)
        mock_coordinator.device.set_mode.assert_awaited_once_with(Mode.HEAT)
        assert entity._optimistic_mode == "heat"

    async def test_set_fan_mode(self, mock_coordinator):
        mock_coordinator.device.set_fan_speed = AsyncMock(
            return_value=CommandResult(success=True, value="quiet")
        )
        entity = _make_climate(mock_coordinator)
        entity.async_write_ha_state = MagicMock()

        await entity.async_set_fan_mode("quiet")
        mock_coordinator.device.set_fan_speed.assert_awaited_once_with(FanSpeed.QUIET)
        assert entity._optimistic_fan_speed == "quiet"

    async def test_set_swing_mode(self, mock_coordinator):
        mock_coordinator.device.set_vane_direction = AsyncMock(
            return_value=CommandResult(success=True, value="swing")
        )
        entity = _make_climate(mock_coordinator)
        entity.async_write_ha_state = MagicMock()

        await entity.async_set_swing_mode("swing")
        mock_coordinator.device.set_vane_direction.assert_awaited_once_with(
            VaneDirection.SWING
        )
        assert entity._optimistic_vane_direction == "swing"


# ── Supported features ──


class TestSupportedFeatures:
    def test_supported_features(self, mock_coordinator):
        """All features present when auto mode and vane are supported."""
        entity = _make_climate(mock_coordinator)
        features = entity.supported_features
        assert features & ClimateEntityFeature.TARGET_TEMPERATURE
        assert features & ClimateEntityFeature.FAN_MODE
        assert features & ClimateEntityFeature.TURN_OFF
        assert features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        assert features & ClimateEntityFeature.SWING_MODE

    def test_supported_features_no_auto(self, mock_coordinator):
        """No TARGET_TEMPERATURE_RANGE when auto mode is not supported."""
        mock_coordinator.device.supported_modes = [Mode.OFF, Mode.COOL, Mode.HEAT]
        entity = _make_climate(mock_coordinator)
        features = entity.supported_features
        assert features & ClimateEntityFeature.TARGET_TEMPERATURE
        assert not (features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE)

    def test_supported_features_no_vane(self, mock_coordinator):
        """No SWING_MODE when vane directions not supported."""
        mock_coordinator.device.supported_vane_directions = []
        entity = _make_climate(mock_coordinator)
        features = entity.supported_features
        assert not (features & ClimateEntityFeature.SWING_MODE)


# ── Min/max temp ──


class TestMinMaxTemp:
    def test_min_max_temp(self, mock_coordinator):
        """Returns device profile limits."""
        mock_coordinator.device.status.mode = "cool"
        entity = _make_climate(mock_coordinator)
        assert entity.min_temp == 18.0
        assert entity.max_temp == 30.0

    def test_min_max_temp_heat(self, mock_coordinator):
        """Returns heat limits in heat mode."""
        mock_coordinator.device.status.mode = "heat"
        entity = _make_climate(mock_coordinator)
        assert entity.min_temp == 16.0
        assert entity.max_temp == 28.0

    @pytest.mark.parametrize("mode", ["auto", "autoCool", "autoHeat"])
    def test_min_max_temp_auto(self, mock_coordinator, mode):
        """Auto modes span the heat and cool limits so both setpoints fit."""
        mock_coordinator.device.status.mode = mode
        entity = _make_climate(mock_coordinator)
        assert entity.min_temp == 16.0
        assert entity.max_temp == 30.0

    def test_min_max_temp_auto_partial_limits(self, mock_coordinator):
        """Auto modes use whichever limits the profile provides."""
        mock_coordinator.device.status.min_heat_setpoint = None
        mock_coordinator.device.status.max_heat_setpoint = None
        mock_coordinator.device.status.mode = "autoHeat"
        entity = _make_climate(mock_coordinator)
        assert entity.min_temp == 18.0
        assert entity.max_temp == 30.0

    def test_min_max_temp_auto_fallback(self, mock_coordinator):
        """Auto modes return HA defaults when no limits are available."""
        mock_coordinator.device.status.min_cool_setpoint = None
        mock_coordinator.device.status.max_cool_setpoint = None
        mock_coordinator.device.status.min_heat_setpoint = None
        mock_coordinator.device.status.max_heat_setpoint = None
        mock_coordinator.device.status.mode = "auto"
        entity = _make_climate(mock_coordinator)
        assert entity.min_temp == 7
        assert entity.max_temp == 35

    def test_min_max_temp_fallback(self, mock_coordinator):
        """Returns HA defaults when profile limits not available."""
        mock_coordinator.device.status.min_cool_setpoint = None
        mock_coordinator.device.status.max_cool_setpoint = None
        mock_coordinator.device.status.min_heat_setpoint = None
        mock_coordinator.device.status.max_heat_setpoint = None
        mock_coordinator.device.status.mode = "cool"
        entity = _make_climate(mock_coordinator)
        # ClimateEntity defaults: min_temp=7, max_temp=35
        assert entity.min_temp == 7
        assert entity.max_temp == 35


# ── Extra state attributes ──


class TestExtraStateAttributes:
    def test_extra_state_attributes_vane_lr(self, mock_coordinator):
        """vane_left_right exposed when present."""
        mock_coordinator.device.status.vane_left_right = "auto"
        entity = _make_climate(mock_coordinator)
        attrs = entity.extra_state_attributes
        assert attrs["vane_left_right"] == "auto"

    def test_extra_state_attributes_no_vane_lr(self, mock_coordinator):
        """No vane_left_right when None."""
        mock_coordinator.device.status.vane_left_right = None
        entity = _make_climate(mock_coordinator)
        attrs = entity.extra_state_attributes
        assert "vane_left_right" not in attrs


# ── Device info ──


class TestDeviceInfo:
    def test_device_info(self, mock_coordinator):
        entity = _make_climate(mock_coordinator)
        info = entity.device_info
        assert ("mitsubishi_comfort", "SERIAL001") in info["identifiers"]
        assert info["name"] == "Living Room"
        assert info["manufacturer"] == "Mitsubishi"
        assert info["sw_version"] == "2.1.0"
        assert info["hw_version"] == "1.0.0"
