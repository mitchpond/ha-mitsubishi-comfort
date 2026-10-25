"""Tests for the Mitsubishi Comfort sensor and binary sensor entities."""

import pytest

from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
@pytest.mark.parametrize(
    ("entity_id", "unique_id", "value"),
    [
        (
            "sensor.living_room_current_temperature",
            "SER001-current-temperature",
            "25.5",
        ),
        ("sensor.living_room_current_humidity", "SER001-current-humidity", "45.0"),
        ("sensor.living_room_wi_fi_signal", "SER001-wifi-signal", "-60"),
        ("sensor.living_room_sensor_battery", "SER001-sensor-battery", "90"),
        ("sensor.living_room_sensor_signal", "SER001-sensor-signal", "-70"),
        ("sensor.living_room_uptime", "SER001-uptime", "7200"),
        ("sensor.bedroom_current_temperature", "SER002-current-temperature", "25.5"),
        ("sensor.outdoor_outdoor_temperature", "SER003-outdoor-temperature", "8.5"),
        ("sensor.outdoor_wi_fi_signal", "SER003-wifi-signal", "-55"),
        ("binary_sensor.living_room_filter_dirty", "SER001-filter-dirty", STATE_OFF),
    ],
)
async def test_entities(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    entity_id: str,
    unique_id: str,
    value: str,
) -> None:
    """Each entity reports its value under the expected unique ID."""
    assert hass.states.get(entity_id).state == value
    assert entity_registry.async_get(entity_id).unique_id == unique_id


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_cloud_unit_has_no_adapter_sensors(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Cloud-controlled units only get temperature and humidity sensors."""
    entities = er.async_entries_for_config_entry(
        entity_registry, init_integration.entry_id
    )
    bedroom = sorted(e.unique_id for e in entities if e.unique_id.startswith("SER002"))
    assert bedroom == [
        "SER002",
        "SER002-current-humidity",
        "SER002-current-temperature",
    ]


async def test_disabled_by_default(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Only the temperature sensor is enabled by default."""
    assert hass.states.get("sensor.living_room_current_temperature") is not None
    entry = entity_registry.async_get("sensor.living_room_uptime")
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
