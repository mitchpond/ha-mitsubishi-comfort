"""Config flow for Mitsubishi Comfort integration."""

import logging
from typing import Any, override

from mitsubishi_comfort import MitsubishiCloudAccount
from mitsubishi_comfort.exceptions import AuthenticationError, DeviceConnectionError
import probatio

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .const import (
    CONF_CONNECT_TIMEOUT,
    CONF_RESPONSE_TIMEOUT,
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_RESPONSE_TIMEOUT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_USERNAME): str,
        probatio.Required(probatio.Secret(CONF_PASSWORD)): str,
    }
)


class MitsubishiComfortOptionsFlow(OptionsFlowWithReload):
    """Handle options flow."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the connection timeouts."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        CONF_CONNECT_TIMEOUT,
                        default=self.config_entry.options.get(
                            CONF_CONNECT_TIMEOUT, DEFAULT_CONNECT_TIMEOUT
                        ),
                    ): probatio.All(probatio.Coerce(float), probatio.Range(min=0.1)),
                    probatio.Required(
                        CONF_RESPONSE_TIMEOUT,
                        default=self.config_entry.options.get(
                            CONF_RESPONSE_TIMEOUT, DEFAULT_RESPONSE_TIMEOUT
                        ),
                    ): probatio.All(probatio.Coerce(float), probatio.Range(min=0.1)),
                }
            ),
        )


class MitsubishiComfortConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle config flow for Mitsubishi Comfort."""

    VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            account = MitsubishiCloudAccount(
                user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            try:
                await account.login()
                devices = await account.discover_devices()
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except DeviceConnectionError, OSError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during setup")
                errors["base"] = "unknown"
            else:
                if devices:
                    return self.async_create_entry(
                        title=user_input[CONF_USERNAME],
                        data={
                            CONF_USERNAME: user_input[CONF_USERNAME],
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                        },
                    )
                errors["base"] = "no_devices"
            finally:
                await account.close()

        return self.async_show_form(
            step_id="user",
            data_schema=USER_SCHEMA,
            errors=errors,
        )

    @override
    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Offer setup when an adapter appears on the network.

        Setup reads DHCP leases itself to find device addresses, so nothing
        from the discovery needs to be kept.
        """
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return await self.async_step_user()

    @staticmethod
    @callback
    @override
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> MitsubishiComfortOptionsFlow:
        """Return the options flow handler."""
        return MitsubishiComfortOptionsFlow()
