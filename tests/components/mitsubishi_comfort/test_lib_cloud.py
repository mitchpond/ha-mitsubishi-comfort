"""Tests for the MitsubishiCloudAccount class."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from aioresponses import aioresponses

from homeassistant.components.mitsubishi_comfort.lib.cloud import (
    MitsubishiCloudAccount,
    _SIO_EVENT,
)
from homeassistant.components.mitsubishi_comfort.lib.const import V3_BASE_URL


def _make_account() -> MitsubishiCloudAccount:
    return MitsubishiCloudAccount("test@test.com", "password123")


class TestLogin:
    async def test_login_success(self):
        """Stores access and refresh tokens on success."""
        account = _make_account()
        with aioresponses() as m:
            m.post(
                f"{V3_BASE_URL}/v3/login",
                payload={
                    "token": {
                        "access": "access_jwt_here",
                        "refresh": "refresh_jwt_here",
                    }
                },
            )
            result = await account.login()

        assert result is True
        assert account._access_token == "access_jwt_here"
        assert account._refresh_token == "refresh_jwt_here"
        await account.close()

    async def test_login_failure(self):
        """Returns False on HTTP error."""
        account = _make_account()
        with aioresponses() as m:
            m.post(f"{V3_BASE_URL}/v3/login", status=401)
            result = await account.login()

        assert result is False
        assert account._access_token is None
        await account.close()


class TestGetSites:
    async def test_get_sites(self):
        """Returns list from REST endpoint."""
        account = _make_account()
        account._access_token = "valid_token"
        with aioresponses() as m:
            m.get(
                f"{V3_BASE_URL}/v3/sites/",
                payload=[
                    {"id": "site1", "name": "Home"},
                    {"id": "site2", "name": "Office"},
                ],
            )
            sites = await account.get_sites()

        assert len(sites) == 2
        assert sites[0]["id"] == "site1"
        await account.close()


class TestAutoRefresh:
    async def test_auto_refresh_on_401(self):
        """Refreshes token and retries on 401."""
        account = _make_account()
        account._access_token = "expired_token"
        account._refresh_token = "valid_refresh"

        with aioresponses() as m:
            # First call returns 401
            m.get(f"{V3_BASE_URL}/v3/sites/", status=401)
            # Refresh succeeds
            m.post(
                f"{V3_BASE_URL}/v3/refresh",
                payload={"access": "new_access", "refresh": "new_refresh"},
            )
            # Retry succeeds
            m.get(
                f"{V3_BASE_URL}/v3/sites/",
                payload=[{"id": "site1"}],
            )
            sites = await account.get_sites()

        assert sites == [{"id": "site1"}]
        assert account._access_token == "new_access"
        await account.close()


class TestDiscoverDevices:
    async def test_discover_devices(self):
        """Full discovery flow returns DeviceInfo dict."""
        account = _make_account()
        account._access_token = "valid_token"

        with aioresponses() as m:
            # get_sites
            m.get(
                f"{V3_BASE_URL}/v3/sites/",
                payload=[{"id": "site1"}],
            )
            # get_zones
            m.get(
                f"{V3_BASE_URL}/v3/sites/site1/zones",
                payload=[
                    {
                        "name": "Living Room",
                        "adapter": {
                            "deviceSerial": "SER001",
                            "unitType": "ductless",
                            "macAddress": "AA:BB:CC:DD:EE:FF",
                        },
                    }
                ],
            )
            # get_device_status for cryptoSerial
            m.get(
                f"{V3_BASE_URL}/v3/devices/SER001/status",
                payload={"cryptoSerial": "0102030405060708090a"},
            )

            # Mock websocket password retrieval
            with patch.object(
                account,
                "get_passwords_via_websocket",
                new=AsyncMock(return_value={"SER001": "dGVzdA=="}),
            ):
                devices = await account.discover_devices()

        assert "SER001" in devices
        assert devices["SER001"].label == "Living Room"
        assert devices["SER001"].crypto_serial == "0102030405060708090a"
        assert devices["SER001"].password == "dGVzdA=="
        await account.close()

    async def test_discover_with_cached_credentials(self):
        """Skips Socket.IO for cached devices."""
        account = _make_account()
        account._access_token = "valid_token"

        cached = {
            "SER001": {
                "password": "cached_pw",
                "crypto_serial": "0102030405060708090a",
                "address": "192.168.1.100",
            }
        }

        with aioresponses() as m:
            m.get(f"{V3_BASE_URL}/v3/sites/", payload=[{"id": "site1"}])
            m.get(
                f"{V3_BASE_URL}/v3/sites/site1/zones",
                payload=[
                    {
                        "name": "Living Room",
                        "adapter": {
                            "deviceSerial": "SER001",
                            "unitType": "ductless",
                            "macAddress": "AA:BB:CC:DD:EE:FF",
                        },
                    }
                ],
            )

            # No websocket call expected because cached credentials include password
            with patch.object(
                account,
                "get_passwords_via_websocket",
                new=AsyncMock(return_value={}),
            ) as ws_mock:
                devices = await account.discover_devices(
                    cached_credentials=cached
                )

        assert "SER001" in devices
        assert devices["SER001"].password == "cached_pw"
        assert devices["SER001"].crypto_serial == "0102030405060708090a"
        # Socket.IO should not have been called
        ws_mock.assert_not_awaited()
        await account.close()


class TestUserIdCached:
    def test_user_id_cached(self):
        """_user_id cached after first decode."""
        account = _make_account()
        # Create a minimal JWT with id=12345
        import base64

        header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=")
        payload = base64.urlsafe_b64encode(
            json.dumps({"id": 12345}).encode()
        ).rstrip(b"=")
        account._access_token = f"{header.decode()}.{payload.decode()}.sig"

        # First call decodes
        uid = account._get_user_id_from_token()
        assert uid == "12345"
        assert account._user_id == "12345"

        # Second call uses cached value
        account._access_token = None  # Would fail if decoded again
        uid2 = account._get_user_id_from_token()
        assert uid2 == "12345"


class TestExtractPasswords:
    def test_extract_passwords_basic(self):
        """Extracts password from adapter_update event."""
        passwords: dict[str, str] = {}
        serials = {"SER001", "SER002"}
        raw = f'{_SIO_EVENT}["adapter_update",{{"deviceSerial":"SER001","password":"pw123"}}]'

        MitsubishiCloudAccount._extract_passwords(raw, passwords, serials)
        assert passwords == {"SER001": "pw123"}

    def test_extract_passwords_ignores_unknown_serial(self):
        """Ignores serials not in the needed set."""
        passwords: dict[str, str] = {}
        serials = {"SER001"}
        raw = f'{_SIO_EVENT}["adapter_update",{{"deviceSerial":"SER999","password":"pw"}}]'

        MitsubishiCloudAccount._extract_passwords(raw, passwords, serials)
        assert passwords == {}
