"""Tests for Mitsubishi Comfort setup and unload."""

from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
from mitsubishi_comfort.exceptions import AuthenticationError, DeviceConnectionError
import pytest

from homeassistant.components.mitsubishi_comfort import LEGACY_CREDENTIAL_CACHE
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_DEVICES, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.json import save_json
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from . import (
    CLOUD_SERIAL,
    LOCAL_SERIAL,
    STATION_SERIAL,
    default_discovery,
    make_device_info,
)

from tests.common import MockConfigEntry, async_fire_time_changed


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_setup_and_unload(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_account: MagicMock,
    mock_devices: dict[str, MagicMock],
) -> None:
    """Local, cloud and station devices are set up, then closed on unload."""
    entry = init_integration
    assert entry.state is ConfigEntryState.LOADED
    assert set(entry.runtime_data.coordinators) == {
        LOCAL_SERIAL,
        CLOUD_SERIAL,
        STATION_SERIAL,
    }
    assert entry.data[CONF_DEVICES][LOCAL_SERIAL]["password"] == "cGFzc3dvcmQ="
    mock_account.discover_devices.assert_awaited_once_with(
        cached_credentials={}, cloud_fallback=True
    )

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    for serial in (LOCAL_SERIAL, CLOUD_SERIAL, STATION_SERIAL):
        mock_devices[serial].close.assert_awaited_once()
    mock_account.close.assert_awaited_once()


@pytest.mark.parametrize(
    ("exception", "state"),
    [
        (AuthenticationError("rejected"), ConfigEntryState.SETUP_ERROR),
        (DeviceConnectionError("offline"), ConfigEntryState.SETUP_RETRY),
    ],
)
async def test_setup_login_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_account: MagicMock,
    mock_devices: dict[str, MagicMock],
    exception: Exception,
    state: ConfigEntryState,
) -> None:
    """Bad credentials fail setup; connection problems retry it."""
    mock_account.login.side_effect = exception
    await _setup(hass, mock_config_entry)
    assert mock_config_entry.state is state
    mock_account.close.assert_awaited_once()


async def test_setup_discovery_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_account: MagicMock,
    mock_devices: dict[str, MagicMock],
) -> None:
    """A failed or empty discovery retries setup."""
    mock_account.discover_devices.side_effect = DeviceConnectionError("offline")
    await _setup(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY

    mock_account.discover_devices.side_effect = lambda **_: {}
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_without_usable_devices(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_account: MagicMock,
    mock_devices: dict[str, MagicMock],
) -> None:
    """Setup retries when no device has local or cloud credentials."""
    mock_account.discover_devices.side_effect = lambda **_: {
        LOCAL_SERIAL: make_device_info(LOCAL_SERIAL, password="", site_id="")
    }
    await _setup(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_cached_credentials_used(
    hass: HomeAssistant,
    mock_account: MagicMock,
    mock_devices: dict[str, MagicMock],
) -> None:
    """Credentials stored in the entry fill in what discovery lacks."""
    cached = {
        LOCAL_SERIAL: {
            "address": "192.0.2.20",
            "password": "Y2FjaGVk",
            "crypto_serial": "0a0b",
        }
    }
    entry = MockConfigEntry(
        domain="mitsubishi_comfort",
        unique_id="mitsubishi_comfort",
        data={"username": "u", "password": "p", CONF_DEVICES: cached},
    )
    mock_account.discover_devices.side_effect = lambda **_: {
        LOCAL_SERIAL: make_device_info(
            LOCAL_SERIAL, address="", password="", crypto_serial=""
        )
    }
    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    mock_account.discover_devices.assert_awaited_once_with(
        cached_credentials=cached, cloud_fallback=True
    )
    kwargs = mock_devices["_indoor_cls"].call_args.kwargs
    assert kwargs["address"] == "192.0.2.20"
    assert kwargs["password_b64"] == "Y2FjaGVk"
    assert kwargs["crypto_serial_hex"] == "0a0b"


async def test_legacy_cache_migrated(
    hass: HomeAssistant,
    tmp_path: Path,
    mock_config_entry: MockConfigEntry,
    mock_account: MagicMock,
    mock_devices: dict[str, MagicMock],
) -> None:
    """The old credential file is read once, stored in the entry and removed."""
    hass.config.config_dir = str(tmp_path)
    path = hass.config.path(LEGACY_CREDENTIAL_CACHE)
    legacy = {LOCAL_SERIAL: {"password": "bGVnYWN5"}}
    await hass.async_add_executor_job(save_json, path, legacy)
    mock_account.discover_devices.side_effect = lambda **_: {
        LOCAL_SERIAL: make_device_info(LOCAL_SERIAL, password="")
    }

    await _setup(hass, mock_config_entry)

    mock_account.discover_devices.assert_awaited_once_with(
        cached_credentials=legacy, cloud_fallback=True
    )
    assert mock_config_entry.data[CONF_DEVICES][LOCAL_SERIAL]["password"] == "bGVnYWN5"
    assert not await hass.async_add_executor_job(Path(path).exists)


async def test_address_found_through_dhcp(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_account: MagicMock,
    mock_devices: dict[str, MagicMock],
) -> None:
    """Devices without an address are matched against DHCP leases."""
    mock_account.discover_devices.side_effect = lambda **_: {
        LOCAL_SERIAL: make_device_info(LOCAL_SERIAL, address="")
    }
    leases = [
        DhcpServiceInfo(ip="192.0.2.30", hostname="kumo", macaddress="24cd8d000001"),
        DhcpServiceInfo(ip="192.0.2.99", hostname="other", macaddress="aabbcc000001"),
    ]
    with (
        patch(
            "homeassistant.components.mitsubishi_comfort.async_discovered_service_info",
            return_value=leases,
        ),
        patch(
            "homeassistant.components.mitsubishi_comfort.probe_candidate_ips",
            return_value={LOCAL_SERIAL: "192.0.2.30"},
        ) as probe,
    ):
        await _setup(hass, mock_config_entry)

    assert probe.call_args.args[1] == ["192.0.2.30"]
    assert mock_devices["_indoor_cls"].call_args.kwargs["address"] == "192.0.2.30"


async def test_retry_switches_cloud_unit_to_lan(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_account: MagicMock,
    mock_devices: dict[str, MagicMock],
) -> None:
    """A password fetched in the background reloads the unit onto the LAN."""

    def discovery(**_):
        devices = default_discovery()
        devices[CLOUD_SERIAL] = make_device_info(CLOUD_SERIAL, password="")
        return devices

    mock_account.discover_devices.side_effect = discovery
    mock_account.get_passwords_via_websocket.return_value = {CLOUD_SERIAL: "bmV3"}

    await _setup(hass, mock_config_entry)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.data[CONF_DEVICES][CLOUD_SERIAL]["password"] == "bmV3"
    local_serials = [
        c.kwargs["serial"] for c in mock_devices["_indoor_cls"].call_args_list
    ]
    assert local_serials == [LOCAL_SERIAL, LOCAL_SERIAL, CLOUD_SERIAL]


async def test_retry_gives_up(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_account: MagicMock,
) -> None:
    """Without new credentials the cloud unit stays on cloud control."""
    assert mock_account.get_passwords_via_websocket.await_count == 3
    assert init_integration.state is ConfigEntryState.LOADED


async def test_unavailable_after_missed_polls(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_devices: dict[str, MagicMock],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A unit becomes unavailable after three missed polls and recovers."""
    entity_id = "climate.living_room"
    mock_devices[LOCAL_SERIAL].update_status.return_value = False

    for _ in range(2):
        freezer.tick(timedelta(seconds=60))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state != STATE_UNAVAILABLE

    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    mock_devices[LOCAL_SERIAL].update_status.return_value = True
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "cool"
