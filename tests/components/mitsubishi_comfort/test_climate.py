"""Tests for the Mitsubishi Comfort climate entity."""

from datetime import timedelta
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from mitsubishi_comfort.types import CommandResult, FanSpeed, Mode, VaneDirection
import pytest

from homeassistant.components.climate import (
    ATTR_CURRENT_HUMIDITY,
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_HVAC_MODES,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_SWING_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_SWING_MODE,
    SERVICE_SET_TEMPERATURE,
    SERVICE_TURN_OFF,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from . import CLOUD_SERIAL, LOCAL_SERIAL

from tests.common import MockConfigEntry, async_fire_time_changed

ENTITY_ID = "climate.living_room"


async def _call(hass: HomeAssistant, service: str, **data) -> None:
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        service,
        {ATTR_ENTITY_ID: ENTITY_ID, **data},
        blocking=True,
    )


async def test_state(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """The climate entity reflects the unit's status."""
    state = hass.states.get(ENTITY_ID)
    assert state.state == HVACMode.COOL
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.COOLING
    assert state.attributes[ATTR_CURRENT_TEMPERATURE] == 25.5
    assert state.attributes[ATTR_CURRENT_HUMIDITY] == 45.0
    assert state.attributes[ATTR_TEMPERATURE] == 24.0
    assert state.attributes[ATTR_FAN_MODE] == "auto"
    assert state.attributes[ATTR_FAN_MODES] == ["auto", "low", "powerful"]
    assert state.attributes[ATTR_SWING_MODE] == "auto"
    assert state.attributes["vane_left_right"] == "center"
    assert HVACMode.HEAT_COOL in state.attributes[ATTR_HVAC_MODES]
    assert entity_registry.async_get(ENTITY_ID).unique_id == LOCAL_SERIAL

    # Cloud-controlled units get a climate entity too.
    assert hass.states.get("climate.bedroom") is not None
    assert entity_registry.async_get("climate.bedroom").unique_id == CLOUD_SERIAL


async def test_set_hvac_mode(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_devices: dict[str, MagicMock],
) -> None:
    """Changing the mode is sent to the unit and shown optimistically."""
    await _call(hass, SERVICE_SET_HVAC_MODE, **{ATTR_HVAC_MODE: HVACMode.HEAT})
    mock_devices[LOCAL_SERIAL].set_mode.assert_awaited_once_with(Mode.HEAT)
    state = hass.states.get(ENTITY_ID)
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_TEMPERATURE] == 20.0

    await _call(hass, SERVICE_TURN_OFF)
    mock_devices[LOCAL_SERIAL].set_mode.assert_awaited_with(Mode.OFF)
    assert hass.states.get(ENTITY_ID).state == HVACMode.OFF


async def test_set_temperature(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_devices: dict[str, MagicMock],
) -> None:
    """A single setpoint follows the mode; a range sets both setpoints."""
    device = mock_devices[LOCAL_SERIAL]
    await _call(hass, SERVICE_SET_TEMPERATURE, **{ATTR_TEMPERATURE: 22.5})
    device.set_cool_setpoint.assert_awaited_once_with(22.5)
    assert hass.states.get(ENTITY_ID).attributes[ATTR_TEMPERATURE] == 22.5

    await _call(hass, SERVICE_SET_HVAC_MODE, **{ATTR_HVAC_MODE: HVACMode.HEAT_COOL})
    await _call(
        hass,
        SERVICE_SET_TEMPERATURE,
        **{ATTR_TARGET_TEMP_LOW: 19.0, ATTR_TARGET_TEMP_HIGH: 26.0},
    )
    device.set_cool_setpoint.assert_awaited_with(26.0)
    device.set_heat_setpoint.assert_awaited_once_with(19.0)
    state = hass.states.get(ENTITY_ID)
    assert state.attributes[ATTR_TARGET_TEMP_LOW] == 19.0
    assert state.attributes[ATTR_TARGET_TEMP_HIGH] == 26.0


async def test_set_fan_and_swing_mode(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_devices: dict[str, MagicMock],
) -> None:
    """Fan speed and vane direction are sent to the unit."""
    await _call(hass, SERVICE_SET_FAN_MODE, **{ATTR_FAN_MODE: "powerful"})
    mock_devices[LOCAL_SERIAL].set_fan_speed.assert_awaited_once_with(FanSpeed.POWERFUL)
    await _call(hass, SERVICE_SET_SWING_MODE, **{ATTR_SWING_MODE: "swing"})
    mock_devices[LOCAL_SERIAL].set_vane_direction.assert_awaited_once_with(
        VaneDirection.SWING
    )
    state = hass.states.get(ENTITY_ID)
    assert state.attributes[ATTR_FAN_MODE] == "powerful"
    assert state.attributes[ATTR_SWING_MODE] == "swing"


@pytest.mark.parametrize(
    ("command", "service", "data"),
    [
        ("set_mode", SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: HVACMode.HEAT}),
        ("set_cool_setpoint", SERVICE_SET_TEMPERATURE, {ATTR_TEMPERATURE: 22}),
        ("set_fan_speed", SERVICE_SET_FAN_MODE, {ATTR_FAN_MODE: "low"}),
        ("set_vane_direction", SERVICE_SET_SWING_MODE, {ATTR_SWING_MODE: "swing"}),
    ],
)
async def test_rejected_command(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_devices: dict[str, MagicMock],
    command: str,
    service: str,
    data: dict,
) -> None:
    """A command the unit rejects raises an error."""
    getattr(mock_devices[LOCAL_SERIAL], command).side_effect = None
    getattr(mock_devices[LOCAL_SERIAL], command).return_value = CommandResult(
        success=False
    )
    with pytest.raises(HomeAssistantError):
        await _call(hass, service, **data)


async def test_temperature_in_mode_without_setpoint(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_devices: dict[str, MagicMock],
) -> None:
    """A single setpoint can't be set in a mode that has none."""
    await _call(hass, SERVICE_SET_HVAC_MODE, **{ATTR_HVAC_MODE: HVACMode.DRY})
    with pytest.raises(HomeAssistantError):
        await _call(hass, SERVICE_SET_TEMPERATURE, **{ATTR_TEMPERATURE: 22})
    mock_devices[LOCAL_SERIAL].set_cool_setpoint.assert_not_awaited()


async def _poll(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, device: MagicMock, **status
) -> None:
    """Update the unit's reported status and run the next coordinator poll."""
    for key, value in status.items():
        setattr(device.status, key, value)
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("mode", "action"),
    [
        ("auto", HVACAction.IDLE),
        ("autoCool", HVACAction.COOLING),
        ("autoHeat", HVACAction.HEATING),
    ],
)
async def test_auto_mode_keeps_range(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_devices: dict[str, MagicMock],
    freezer: FrozenDateTimeFactory,
    mode: str,
    action: HVACAction,
) -> None:
    """Auto mode shows only the range, even once the unit cools or heats."""
    await _call(hass, SERVICE_SET_HVAC_MODE, **{ATTR_HVAC_MODE: HVACMode.HEAT_COOL})
    state = hass.states.get(ENTITY_ID)
    assert state.state == HVACMode.HEAT_COOL
    assert state.attributes[ATTR_TEMPERATURE] is None

    await _poll(hass, freezer, mock_devices[LOCAL_SERIAL], mode=mode)
    state = hass.states.get(ENTITY_ID)
    assert state.state == HVACMode.HEAT_COOL
    assert state.attributes[ATTR_HVAC_ACTION] == action
    assert state.attributes[ATTR_TEMPERATURE] is None
    assert state.attributes[ATTR_TARGET_TEMP_LOW] == 20.0
    assert state.attributes[ATTR_TARGET_TEMP_HIGH] == 24.0
    assert state.attributes[ATTR_MIN_TEMP] == 10.0
    assert state.attributes[ATTR_MAX_TEMP] == 31.0


@pytest.mark.parametrize(
    ("mode", "min_temp", "max_temp"),
    [
        ("cool", 16.0, 31.0),
        ("heat", 10.0, 31.0),
        ("dry", 16.0, 31.0),
    ],
)
async def test_single_mode_limits(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_devices: dict[str, MagicMock],
    freezer: FrozenDateTimeFactory,
    mode: str,
    min_temp: float,
    max_temp: float,
) -> None:
    """Outside auto, the limits follow the mode's own range."""
    await _poll(
        hass, freezer, mock_devices[LOCAL_SERIAL], mode=mode, max_heat_setpoint=28.0
    )
    state = hass.states.get(ENTITY_ID)
    assert state.attributes[ATTR_MIN_TEMP] == min_temp
    assert state.attributes[ATTR_MAX_TEMP] == (28.0 if mode == "heat" else max_temp)


async def test_auto_mode_limits_prefer_auto_range(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_devices: dict[str, MagicMock],
    freezer: FrozenDateTimeFactory,
) -> None:
    """The unit's own auto limits take priority when it reports them."""
    await _poll(
        hass,
        freezer,
        mock_devices[LOCAL_SERIAL],
        mode="autoHeat",
        min_auto_setpoint=17.0,
        max_auto_setpoint=29.0,
    )
    state = hass.states.get(ENTITY_ID)
    assert state.attributes[ATTR_MIN_TEMP] == 17.0
    assert state.attributes[ATTR_MAX_TEMP] == 29.0


@pytest.mark.parametrize(
    ("limits", "min_temp", "max_temp"),
    [
        ({"min_heat_setpoint": None, "max_heat_setpoint": None}, 16.0, 31.0),
        (
            {
                "min_heat_setpoint": None,
                "max_heat_setpoint": None,
                "min_cool_setpoint": None,
                "max_cool_setpoint": None,
            },
            7.0,
            35.0,
        ),
    ],
)
async def test_auto_mode_limits_fallback(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_devices: dict[str, MagicMock],
    freezer: FrozenDateTimeFactory,
    limits: dict[str, None],
    min_temp: float,
    max_temp: float,
) -> None:
    """Auto mode uses whichever limits exist, then Home Assistant's defaults."""
    await _poll(hass, freezer, mock_devices[LOCAL_SERIAL], mode="auto", **limits)
    state = hass.states.get(ENTITY_ID)
    assert state.attributes[ATTR_MIN_TEMP] == min_temp
    assert state.attributes[ATTR_MAX_TEMP] == max_temp


@pytest.mark.parametrize(
    ("mode", "command", "other"),
    [
        ("autoCool", "set_cool_setpoint", "set_heat_setpoint"),
        ("autoHeat", "set_heat_setpoint", "set_cool_setpoint"),
    ],
)
async def test_single_temperature_in_auto_stage(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_devices: dict[str, MagicMock],
    freezer: FrozenDateTimeFactory,
    mode: str,
    command: str,
    other: str,
) -> None:
    """A single temperature in an auto stage sets that stage's setpoint."""
    device = mock_devices[LOCAL_SERIAL]
    await _poll(hass, freezer, device, mode=mode)
    await _call(hass, SERVICE_SET_TEMPERATURE, **{ATTR_TEMPERATURE: 22.0})
    getattr(device, command).assert_awaited_once_with(22.0)
    getattr(device, other).assert_not_awaited()
    state = hass.states.get(ENTITY_ID)
    assert state.attributes[ATTR_TEMPERATURE] is None
    low_or_high = ATTR_TARGET_TEMP_HIGH if mode == "autoCool" else ATTR_TARGET_TEMP_LOW
    assert state.attributes[low_or_high] == 22.0


async def test_set_range_in_auto_stage(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_devices: dict[str, MagicMock],
    freezer: FrozenDateTimeFactory,
) -> None:
    """The range can be changed while auto mode is heating."""
    device = mock_devices[LOCAL_SERIAL]
    await _poll(hass, freezer, device, mode="autoHeat")
    await _call(
        hass,
        SERVICE_SET_TEMPERATURE,
        **{ATTR_TARGET_TEMP_LOW: 19.0, ATTR_TARGET_TEMP_HIGH: 26.0},
    )
    device.set_heat_setpoint.assert_awaited_once_with(19.0)
    device.set_cool_setpoint.assert_awaited_once_with(26.0)
    state = hass.states.get(ENTITY_ID)
    assert state.attributes[ATTR_TEMPERATURE] is None
    assert state.attributes[ATTR_TARGET_TEMP_LOW] == 19.0
    assert state.attributes[ATTR_TARGET_TEMP_HIGH] == 26.0


async def test_set_temperature_in_heat_mode(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_devices: dict[str, MagicMock],
) -> None:
    """In heat mode a single temperature sets the heat setpoint."""
    device = mock_devices[LOCAL_SERIAL]
    await _call(hass, SERVICE_SET_HVAC_MODE, **{ATTR_HVAC_MODE: HVACMode.HEAT})
    await _call(hass, SERVICE_SET_TEMPERATURE, **{ATTR_TEMPERATURE: 19.5})
    device.set_heat_setpoint.assert_awaited_once_with(19.5)
    state = hass.states.get(ENTITY_ID)
    assert state.attributes[ATTR_TEMPERATURE] == 19.5
    assert state.attributes[ATTR_TARGET_TEMP_LOW] is None
