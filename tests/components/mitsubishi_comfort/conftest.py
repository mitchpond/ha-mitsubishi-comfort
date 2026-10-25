"""Fixtures for Mitsubishi Comfort tests."""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from mitsubishi_comfort import CloudIndoorUnit, IndoorUnit, KumoStation
from mitsubishi_comfort.types import DeviceInfo
import pytest

from homeassistant.components.mitsubishi_comfort.const import DOMAIN
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import default_discovery, make_device

from tests.common import MockConfigEntry


@pytest.fixture(autouse=True)
def no_retry_delay() -> Generator[None]:
    """Run the background credential retry without waiting."""
    with patch("homeassistant.components.mitsubishi_comfort.RETRY_DELAY", 0):
        yield


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return the config entry for a Kumo Cloud account."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="user@example.com",
        unique_id=DOMAIN,
        data={CONF_USERNAME: "user@example.com", CONF_PASSWORD: "secret"},
    )


@pytest.fixture
def mock_account() -> Generator[MagicMock]:
    """Patch the cloud account used by setup and the config flow."""
    account = MagicMock()
    account.login = AsyncMock()
    account.discover_devices = AsyncMock(side_effect=lambda **_: default_discovery())
    account.get_passwords_via_websocket = AsyncMock(return_value={})
    account.close = AsyncMock()
    with (
        patch(
            "homeassistant.components.mitsubishi_comfort.MitsubishiCloudAccount",
            return_value=account,
        ),
        patch(
            "homeassistant.components.mitsubishi_comfort.config_flow.MitsubishiCloudAccount",
            return_value=account,
        ),
    ):
        yield account


@pytest.fixture
def mock_devices() -> Generator[dict[str, MagicMock]]:
    """Patch the device classes, returning one mock device per serial."""
    devices: dict[str, MagicMock] = {}

    def local(cls: type) -> Any:
        def factory(*, name: str, serial: str, **_: Any) -> MagicMock:
            devices[serial] = make_device(cls, serial, name)
            return devices[serial]

        return factory

    def cloud(info: DeviceInfo, account: Any) -> MagicMock:
        devices[info.serial] = make_device(CloudIndoorUnit, info.serial, info.label)
        return devices[info.serial]

    with (
        patch(
            "homeassistant.components.mitsubishi_comfort.IndoorUnit",
            side_effect=local(IndoorUnit),
        ) as indoor,
        patch(
            "homeassistant.components.mitsubishi_comfort.KumoStation",
            side_effect=local(KumoStation),
        ),
        patch(
            "homeassistant.components.mitsubishi_comfort.CloudIndoorUnit",
            side_effect=cloud,
        ),
    ):
        devices["_indoor_cls"] = indoor
        yield devices


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_account: MagicMock,
    mock_devices: dict[str, MagicMock],
) -> MockConfigEntry:
    """Set up the integration with the default devices."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return mock_config_entry
