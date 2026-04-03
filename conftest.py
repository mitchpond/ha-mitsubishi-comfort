"""Root conftest — inject stub HA modules so the integration code can import.

The local homeassistant/ directory contains the actual integration code under
homeassistant/components/mitsubishi_comfort/. We need to make all the HA
framework modules (homeassistant.core, homeassistant.config_entries, etc.)
available as stubs, while still allowing the real integration code to import.
"""

from __future__ import annotations

import os
import sys
import types
from enum import Enum
from unittest.mock import MagicMock
from typing import Any


# ── Helper ──


def _stub(name: str, attrs: dict | None = None) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__path__ = []
    if attrs:
        for k, v in attrs.items():
            setattr(mod, k, v)
    return mod


# ── HA constants ──


class Platform(str, Enum):
    BINARY_SENSOR = "binary_sensor"
    CLIMATE = "climate"
    SENSOR = "sensor"


CONF_USERNAME = "username"
CONF_PASSWORD = "password"
ATTR_TEMPERATURE = "temperature"


class UnitOfTemperature:
    CELSIUS = "\u00b0C"
    FAHRENHEIT = "\u00b0F"


PERCENTAGE = "%"
SIGNAL_STRENGTH_DECIBELS = "dB"


# ── HA core stubs ──


class HomeAssistant:
    def __init__(self):
        self.data = {}
        self.config = MagicMock()
        self.loop = None


def callback(func):
    return func


# ── config_entries stubs ──


class ConfigEntry:
    def __init__(self):
        self.data = {}
        self.options = {}
        self.entry_id = "test_entry_id"


class ConfigFlow:
    VERSION = 1
    hass = None

    def __init_subclass__(cls, *, domain: str = "", **kwargs):
        super().__init_subclass__(**kwargs)

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}

    async def async_set_unique_id(self, uid):
        pass

    def _abort_if_unique_id_configured(self):
        pass


class OptionsFlow:
    config_entry = None

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}


# ── exceptions ──


class ConfigEntryNotReady(Exception):
    pass


# ── helpers.entity ──


class DeviceInfo(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class EntityCategory(str, Enum):
    CONFIG = "config"
    DIAGNOSTIC = "diagnostic"


# ── helpers.update_coordinator ──


class CoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator

    def __class_getitem__(cls, item):
        return cls

    def _handle_coordinator_update(self):
        self.async_write_ha_state()

    def async_write_ha_state(self):
        pass


class DataUpdateCoordinator:
    def __init__(self, hass, logger, *, name, update_interval):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval

    def __class_getitem__(cls, item):
        return cls

    async def _async_update_data(self):
        raise NotImplementedError


class UpdateFailed(Exception):
    pass


# ── climate ──


class ClimateEntityFeature:
    TARGET_TEMPERATURE = 1
    FAN_MODE = 8
    SWING_MODE = 32
    TURN_OFF = 4096
    TARGET_TEMPERATURE_RANGE = 2
    TURN_ON = 8192


class HVACMode(str, Enum):
    OFF = "off"
    COOL = "cool"
    HEAT = "heat"
    DRY = "dry"
    FAN_ONLY = "fan_only"
    HEAT_COOL = "heat_cool"
    AUTO = "auto"


class HVACAction(str, Enum):
    OFF = "off"
    COOLING = "cooling"
    HEATING = "heating"
    DRYING = "drying"
    FAN = "fan"
    IDLE = "idle"
    PREHEATING = "preheating"


class ClimateEntity:
    _enable_turn_on_off_backwards_compatibility = True
    _attr_name = None
    _attr_unique_id = None
    hass = None

    @property
    def min_temp(self):
        return 7

    @property
    def max_temp(self):
        return 35

    def async_write_ha_state(self):
        pass


# ── sensor ──


class SensorDeviceClass(str, Enum):
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    SIGNAL_STRENGTH = "signal_strength"
    BATTERY = "battery"
    DURATION = "duration"


class SensorEntity:
    _attr_device_class = None
    _attr_native_unit_of_measurement = None
    _attr_entity_registry_enabled_default = True
    _attr_entity_category = None
    _attr_unique_id = None
    _attr_name = None
    hass = None


# ── binary_sensor ──


class BinarySensorDeviceClass(str, Enum):
    PROBLEM = "problem"


class BinarySensorEntity:
    _attr_unique_id = None
    _attr_name = None
    hass = None


# ── json helpers ──


def load_json(path):
    return {}


def save_json(path, data):
    pass


# ── Register stubs into sys.modules BEFORE any test collection ──

_project_root = os.path.dirname(os.path.abspath(__file__))
_ha_components_path = os.path.join(_project_root, "homeassistant", "components")

_modules = {
    "homeassistant.const": _stub("homeassistant.const", {
        "Platform": Platform,
        "CONF_USERNAME": CONF_USERNAME,
        "CONF_PASSWORD": CONF_PASSWORD,
        "ATTR_TEMPERATURE": ATTR_TEMPERATURE,
        "UnitOfTemperature": UnitOfTemperature,
        "PERCENTAGE": PERCENTAGE,
        "SIGNAL_STRENGTH_DECIBELS": SIGNAL_STRENGTH_DECIBELS,
    }),
    "homeassistant.core": _stub("homeassistant.core", {
        "HomeAssistant": HomeAssistant,
        "callback": callback,
    }),
    "homeassistant.config_entries": _stub("homeassistant.config_entries", {
        "ConfigEntry": ConfigEntry,
        "ConfigFlow": ConfigFlow,
        "OptionsFlow": OptionsFlow,
    }),
    "homeassistant.exceptions": _stub("homeassistant.exceptions", {
        "ConfigEntryNotReady": ConfigEntryNotReady,
    }),
    "homeassistant.helpers": _stub("homeassistant.helpers"),
    "homeassistant.helpers.entity": _stub("homeassistant.helpers.entity", {
        "DeviceInfo": DeviceInfo,
        "EntityCategory": EntityCategory,
    }),
    "homeassistant.helpers.entity_platform": _stub("homeassistant.helpers.entity_platform", {
        "AddEntitiesCallback": Any,
    }),
    "homeassistant.helpers.update_coordinator": _stub("homeassistant.helpers.update_coordinator", {
        "CoordinatorEntity": CoordinatorEntity,
        "DataUpdateCoordinator": DataUpdateCoordinator,
        "UpdateFailed": UpdateFailed,
    }),
    "homeassistant.helpers.json": _stub("homeassistant.helpers.json", {
        "save_json": save_json,
    }),
    "homeassistant.util": _stub("homeassistant.util"),
    "homeassistant.util.json": _stub("homeassistant.util.json", {
        "load_json": load_json,
    }),
    "homeassistant.components.climate": _stub("homeassistant.components.climate", {
        "ClimateEntity": ClimateEntity,
        "ClimateEntityFeature": ClimateEntityFeature,
        "HVACMode": HVACMode,
        "HVACAction": HVACAction,
    }),
    "homeassistant.components.climate.const": _stub("homeassistant.components.climate.const", {
        "ClimateEntityFeature": ClimateEntityFeature,
        "HVACMode": HVACMode,
        "HVACAction": HVACAction,
    }),
    "homeassistant.components.sensor": _stub("homeassistant.components.sensor", {
        "SensorDeviceClass": SensorDeviceClass,
        "SensorEntity": SensorEntity,
    }),
    "homeassistant.components.binary_sensor": _stub("homeassistant.components.binary_sensor", {
        "BinarySensorDeviceClass": BinarySensorDeviceClass,
        "BinarySensorEntity": BinarySensorEntity,
    }),
}

# Register everything except homeassistant.components (we need the real one)
for name, mod in _modules.items():
    sys.modules[name] = mod

# The homeassistant.components module must keep its __path__ pointing to the
# real directory so that homeassistant.components.mitsubishi_comfort resolves.
if "homeassistant.components" not in sys.modules:
    comp_mod = _stub("homeassistant.components")
    comp_mod.__path__ = [_ha_components_path]
    sys.modules["homeassistant.components"] = comp_mod
else:
    existing = sys.modules["homeassistant.components"]
    if hasattr(existing, "__path__"):
        if _ha_components_path not in list(existing.__path__):
            existing.__path__.append(_ha_components_path)
    else:
        existing.__path__ = [_ha_components_path]

# Ensure homeassistant.components is accessible via getattr for patch()
import homeassistant
if not hasattr(homeassistant, "components"):
    homeassistant.components = sys.modules["homeassistant.components"]

# Also ensure voluptuous is available as a mock
vol_mock = MagicMock()
vol_mock.Schema = lambda *a, **kw: MagicMock()
vol_mock.Required = lambda *a, **kw: a[0] if a else "key"
vol_mock.Coerce = lambda *a, **kw: a[0] if a else float
sys.modules["voluptuous"] = vol_mock
