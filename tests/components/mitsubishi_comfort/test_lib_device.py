"""Tests for the Device base class."""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aioresponses import aioresponses

from homeassistant.components.mitsubishi_comfort.lib.device import Device


# Valid base64 password and valid hex crypto serial (>= 9 bytes)
VALID_PASSWORD_B64 = "dGVzdHBhc3N3b3Jk"  # "testpassword"
VALID_CRYPTO_HEX = "0102030405060708090a"  # 10 bytes


def _make_device(
    address: str | None = "192.168.1.100",
    password_b64: str = VALID_PASSWORD_B64,
    crypto_serial_hex: str = VALID_CRYPTO_HEX,
) -> Device:
    return Device(
        name="Test Unit",
        address=address,
        password_b64=password_b64,
        crypto_serial_hex=crypto_serial_hex,
        serial="TEST001",
    )


class TestRequest:
    async def test_request_no_address(self):
        """Returns {} when address is None."""
        device = _make_device(address=None)
        result = await device.request(b'{"c":{}}')
        assert result == {}
        await device.close()

    async def test_request_success(self):
        """Returns parsed JSON on success."""
        device = _make_device()
        with aioresponses() as m:
            m.put(
                re.compile(r"^http://192\.168\.1\.100/api"),
                payload={"r": {"indoorUnit": {"status": {"mode": "cool"}}}},
            )
            result = await device.request(b'{"c":{"indoorUnit":{"status":{}}}}')
        assert "r" in result
        assert result["r"]["indoorUnit"]["status"]["mode"] == "cool"
        await device.close()

    async def test_request_timeout(self):
        """Returns {} on timeout."""
        device = _make_device()
        with aioresponses() as m:
            m.put(re.compile(r"^http://192\.168\.1\.100/api"), exception=TimeoutError())
            result = await device.request(b'{"c":{}}')
        assert result == {}
        await device.close()

    async def test_session_reuse(self):
        """Second request reuses same session."""
        device = _make_device()
        with aioresponses() as m:
            m.put(re.compile(r"^http://192\.168\.1\.100/api"), payload={"r": {}})
            m.put(re.compile(r"^http://192\.168\.1\.100/api"), payload={"r": {}})
            await device.request(b'{"c":{}}')
            session1 = device._session
            await device.request(b'{"c":{}}')
            session2 = device._session
        assert session1 is session2
        await device.close()

    async def test_close_session(self):
        """close() closes the session."""
        device = _make_device()
        with aioresponses() as m:
            m.put(re.compile(r"^http://192\.168\.1\.100/api"), payload={"r": {}})
            await device.request(b'{"c":{}}')
        assert device._session is not None
        await device.close()
        assert device._session is None


class TestInvalidCredentials:
    def test_invalid_base64_disables_device(self):
        """Bad base64 password sets address to None."""
        device = _make_device(password_b64="!!!invalid!!!")
        assert device.address is None

    def test_invalid_hex_disables_device(self):
        """Bad hex crypto serial sets address to None."""
        device = _make_device(crypto_serial_hex="not-hex")
        assert device.address is None

    def test_valid_credentials(self):
        """Valid credentials keep address."""
        device = _make_device()
        assert device.address == "192.168.1.100"
