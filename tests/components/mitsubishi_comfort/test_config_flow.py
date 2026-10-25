"""Tests for the Mitsubishi Comfort config flow."""

from unittest.mock import MagicMock

from mitsubishi_comfort.exceptions import AuthenticationError, DeviceConnectionError
import pytest

from homeassistant.components.mitsubishi_comfort.const import (
    CONF_CONNECT_TIMEOUT,
    CONF_RESPONSE_TIMEOUT,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_DHCP, SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from tests.common import MockConfigEntry

USER_INPUT = {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "secret"}


async def test_user_flow(
    hass: HomeAssistant, mock_account: MagicMock, mock_devices: dict
) -> None:
    """Valid credentials create an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "user@example.com"
    assert result["data"] == USER_INPUT
    assert result["result"].unique_id == DOMAIN
    mock_account.close.assert_awaited()


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (AuthenticationError("rejected"), "invalid_auth"),
        (DeviceConnectionError("offline"), "cannot_connect"),
        (OSError, "cannot_connect"),
        (RuntimeError, "unknown"),
    ],
)
async def test_user_flow_login_errors(
    hass: HomeAssistant,
    mock_account: MagicMock,
    mock_devices: dict,
    side_effect: Exception,
    error: str,
) -> None:
    """Login errors are shown on the form, and the flow can recover."""
    mock_account.login.side_effect = side_effect
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data=USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_account.login.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_no_devices(
    hass: HomeAssistant, mock_account: MagicMock, mock_devices: dict
) -> None:
    """An account without devices is reported, and the flow can recover."""
    mock_account.discover_devices.side_effect = lambda **_: {}
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data=USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_devices"}

    mock_account.discover_devices.side_effect = None
    mock_account.discover_devices.return_value = {"SER001": object()}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_single_instance(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Only one account can be configured."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_dhcp_discovery(
    hass: HomeAssistant, mock_account: MagicMock, mock_devices: dict
) -> None:
    """A discovered adapter offers the sign-in form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_DHCP},
        data=DhcpServiceInfo(
            ip="192.0.2.30", hostname="kumo", macaddress="24cd8d000001"
        ),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_options_flow(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Options are saved and the entry reloads."""
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_CONNECT_TIMEOUT: 2.0, CONF_RESPONSE_TIMEOUT: 10.0},
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options == {
        CONF_CONNECT_TIMEOUT: 2.0,
        CONF_RESPONSE_TIMEOUT: 10.0,
    }
