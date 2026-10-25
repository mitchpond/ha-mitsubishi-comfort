"""Constants for the Mitsubishi Comfort integration."""

from datetime import timedelta
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "mitsubishi_comfort"
PLATFORMS: Final = [Platform.BINARY_SENSOR, Platform.CLIMATE, Platform.SENSOR]
DEFAULT_SCAN_INTERVAL = timedelta(seconds=60)

CONF_CONNECT_TIMEOUT: Final = "connect_timeout"
CONF_RESPONSE_TIMEOUT: Final = "response_timeout"
DEFAULT_CONNECT_TIMEOUT: Final = 1.2
DEFAULT_RESPONSE_TIMEOUT: Final = 8.0

# Must match the "dhcp" matchers in manifest.json.
DHCP_MAC_PREFIXES: Final = ("24cd8d", "7087a7")
