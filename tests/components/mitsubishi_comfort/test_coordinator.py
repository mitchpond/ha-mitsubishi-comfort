"""Tests for the Mitsubishi Comfort coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from homeassistant.components.mitsubishi_comfort.coordinator import (
    MAX_FAILURES_BEFORE_UNAVAILABLE,
    MitsubishiComfortCoordinator,
)


def _make_coordinator(device: MagicMock) -> MitsubishiComfortCoordinator:
    """Create a coordinator with a mocked hass object."""
    hass = MagicMock()
    hass.loop = None
    with patch.object(MitsubishiComfortCoordinator, "__init__", lambda self, *a, **kw: None):
        coordinator = MitsubishiComfortCoordinator.__new__(MitsubishiComfortCoordinator)
    coordinator.device = device
    coordinator._consecutive_failures = 0
    coordinator.logger = MagicMock()
    return coordinator


class TestUpdateSuccess:
    async def test_update_success(self):
        """consecutive_failures reset to 0 after successful update."""
        device = MagicMock()
        device.update_status = AsyncMock(return_value=True)
        device.name = "Test"
        device.serial = "S001"
        coordinator = _make_coordinator(device)
        coordinator._consecutive_failures = 2

        await coordinator._async_update_data()
        assert coordinator._consecutive_failures == 0

    async def test_update_failure_increments(self):
        """consecutive_failures increments on failure."""
        device = MagicMock()
        device.update_status = AsyncMock(return_value=False)
        device.name = "Test"
        device.serial = "S001"
        coordinator = _make_coordinator(device)

        await coordinator._async_update_data()
        assert coordinator._consecutive_failures == 1

    async def test_available_after_success(self):
        """available returns True after successful update."""
        device = MagicMock()
        device.update_status = AsyncMock(return_value=True)
        device.name = "Test"
        device.serial = "S001"
        coordinator = _make_coordinator(device)

        await coordinator._async_update_data()
        assert coordinator.available is True

    async def test_unavailable_after_three_failures(self):
        """available returns False after MAX_FAILURES_BEFORE_UNAVAILABLE failures."""
        device = MagicMock()
        device.update_status = AsyncMock(return_value=False)
        device.name = "Test"
        device.serial = "S001"
        coordinator = _make_coordinator(device)

        for i in range(MAX_FAILURES_BEFORE_UNAVAILABLE - 1):
            await coordinator._async_update_data()

        assert coordinator.available is True

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

        assert coordinator.available is False

    async def test_recovery_after_failure(self):
        """available returns True after recovery from failures."""
        device = MagicMock()
        device.name = "Test"
        device.serial = "S001"
        coordinator = _make_coordinator(device)

        # Fail twice
        device.update_status = AsyncMock(return_value=False)
        await coordinator._async_update_data()
        await coordinator._async_update_data()
        assert coordinator._consecutive_failures == 2
        assert coordinator.available is True

        # Succeed
        device.update_status = AsyncMock(return_value=True)
        await coordinator._async_update_data()
        assert coordinator._consecutive_failures == 0
        assert coordinator.available is True

    async def test_raises_update_failed_at_threshold(self):
        """Raises UpdateFailed when reaching MAX_FAILURES_BEFORE_UNAVAILABLE."""
        device = MagicMock()
        device.update_status = AsyncMock(return_value=False)
        device.name = "Test"
        device.serial = "S001"
        coordinator = _make_coordinator(device)
        coordinator._consecutive_failures = MAX_FAILURES_BEFORE_UNAVAILABLE - 1

        with pytest.raises(UpdateFailed, match="unavailable after"):
            await coordinator._async_update_data()
