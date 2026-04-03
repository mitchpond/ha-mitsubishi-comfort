"""Tests for the Mitsubishi Comfort binary sensor entities."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from homeassistant.components.mitsubishi_comfort.binary_sensor import (
    MitsubishiComfortFilterDirtySensor,
)


def _make_filter_sensor(coordinator: MagicMock) -> MitsubishiComfortFilterDirtySensor:
    """Create a filter dirty sensor bypassing CoordinatorEntity init."""
    entity = MitsubishiComfortFilterDirtySensor.__new__(
        MitsubishiComfortFilterDirtySensor
    )
    entity.coordinator = coordinator
    entity._device = coordinator.device
    entity._attr_unique_id = f"{coordinator.device.serial}-filter-dirty"
    entity._attr_name = f"{coordinator.device.name} Filter Dirty"
    entity.hass = None
    return entity


class TestFilterDirtySensor:
    def test_filter_dirty_on(self, mock_coordinator):
        """is_on returns True when filter dirty."""
        mock_coordinator.device.status.filter_dirty = True
        entity = _make_filter_sensor(mock_coordinator)
        assert entity.is_on is True

    def test_filter_dirty_off(self, mock_coordinator):
        """is_on returns False when filter clean."""
        mock_coordinator.device.status.filter_dirty = False
        entity = _make_filter_sensor(mock_coordinator)
        assert entity.is_on is False

    def test_filter_dirty_none(self, mock_coordinator):
        """is_on returns None when status unknown."""
        mock_coordinator.device.status.filter_dirty = None
        entity = _make_filter_sensor(mock_coordinator)
        assert entity.is_on is None
