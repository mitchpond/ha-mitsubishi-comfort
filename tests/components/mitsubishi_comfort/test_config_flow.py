"""Tests for the Mitsubishi Comfort config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.components.mitsubishi_comfort.lib.exceptions import AuthenticationError
from homeassistant.components.mitsubishi_comfort.lib.types import DeviceInfo


class TestUserStep:
    """Test the user config flow step logic."""

    async def test_user_step_shows_form(self):
        """Initial step with no input shows a form."""
        from homeassistant.components.mitsubishi_comfort.config_flow import (
            MitsubishiComfortConfigFlow,
        )

        flow = MitsubishiComfortConfigFlow.__new__(MitsubishiComfortConfigFlow)
        flow.hass = MagicMock()

        result = await flow.async_step_user(user_input=None)
        assert result["type"] == "form"
        assert result["step_id"] == "user"

    async def test_user_step_invalid_auth(self):
        """A rejected login shows invalid_auth error."""
        from homeassistant.components.mitsubishi_comfort.config_flow import (
            MitsubishiComfortConfigFlow,
        )

        flow = MitsubishiComfortConfigFlow.__new__(MitsubishiComfortConfigFlow)
        flow.hass = MagicMock()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()

        with patch(
            "homeassistant.components.mitsubishi_comfort.config_flow.MitsubishiCloudAccount"
        ) as mock_cls:
            account = AsyncMock()
            account.login = AsyncMock(side_effect=AuthenticationError("rejected"))
            mock_cls.return_value = account

            result = await flow.async_step_user(
                user_input={"username": "test@test.com", "password": "wrong"}
            )

        assert result["type"] == "form"
        assert result["errors"] == {"base": "invalid_auth"}

    async def test_user_step_cannot_connect(self):
        """OSError shows cannot_connect error."""
        from homeassistant.components.mitsubishi_comfort.config_flow import (
            MitsubishiComfortConfigFlow,
        )

        flow = MitsubishiComfortConfigFlow.__new__(MitsubishiComfortConfigFlow)
        flow.hass = MagicMock()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()

        with patch(
            "homeassistant.components.mitsubishi_comfort.config_flow.MitsubishiCloudAccount"
        ) as mock_cls:
            account = AsyncMock()
            account.login = AsyncMock(side_effect=OSError("Connection refused"))
            mock_cls.return_value = account

            result = await flow.async_step_user(
                user_input={"username": "test@test.com", "password": "pass"}
            )

        assert result["type"] == "form"
        assert result["errors"] == {"base": "cannot_connect"}

    async def test_user_step_success(self):
        """Successful login creates entry."""
        from homeassistant.components.mitsubishi_comfort.config_flow import (
            MitsubishiComfortConfigFlow,
        )

        flow = MitsubishiComfortConfigFlow.__new__(MitsubishiComfortConfigFlow)
        flow.hass = MagicMock()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        flow.async_create_entry = MagicMock(
            return_value={"type": "create_entry", "title": "test@test.com"}
        )

        with patch(
            "homeassistant.components.mitsubishi_comfort.config_flow.MitsubishiCloudAccount"
        ) as mock_cls:
            account = AsyncMock()
            account.login = AsyncMock(return_value=True)
            account.discover_devices = AsyncMock(
                return_value={
                    "S1": DeviceInfo(
                        serial="S1",
                        label="Unit",
                        address="1.2.3.4",
                        mac="AA:BB:CC:DD:EE:FF",
                        unit_type="ductless",
                        password="pw",
                        crypto_serial="0102030405060708090a",
                    )
                }
            )
            mock_cls.return_value = account

            result = await flow.async_step_user(
                user_input={"username": "test@test.com", "password": "pass"}
            )

        assert result["type"] == "create_entry"
        flow.async_create_entry.assert_called_once()

    async def test_user_step_no_devices(self):
        """Successful login but no devices shows cannot_connect."""
        from homeassistant.components.mitsubishi_comfort.config_flow import (
            MitsubishiComfortConfigFlow,
        )

        flow = MitsubishiComfortConfigFlow.__new__(MitsubishiComfortConfigFlow)
        flow.hass = MagicMock()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()

        with patch(
            "homeassistant.components.mitsubishi_comfort.config_flow.MitsubishiCloudAccount"
        ) as mock_cls:
            account = AsyncMock()
            account.login = AsyncMock(return_value=True)
            account.discover_devices = AsyncMock(return_value={})
            mock_cls.return_value = account

            result = await flow.async_step_user(
                user_input={"username": "test@test.com", "password": "pass"}
            )

        assert result["type"] == "form"
        assert result["errors"] == {"base": "cannot_connect"}


class TestDHCPStep:
    async def test_dhcp_step_stores_ip(self):
        """DHCP discovery stores IP in hass.data."""
        from homeassistant.components.mitsubishi_comfort.config_flow import (
            MitsubishiComfortConfigFlow,
        )

        flow = MitsubishiComfortConfigFlow.__new__(MitsubishiComfortConfigFlow)
        flow.hass = MagicMock()
        flow.hass.data = {}
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        # async_step_user will be called at the end of async_step_dhcp
        flow.async_step_user = AsyncMock(
            return_value={"type": "form", "step_id": "user"}
        )

        discovery = MagicMock()
        discovery.ip = "192.168.1.50"
        discovery.macaddress = "AA:BB:CC:DD:EE:FF"

        await flow.async_step_dhcp(discovery)

        assert "mitsubishi_comfort_dhcp_discovered" in flow.hass.data
        assert (
            flow.hass.data["mitsubishi_comfort_dhcp_discovered"]["AA:BB:CC:DD:EE:FF"]
            == "192.168.1.50"
        )
