"""Config flow for SK-Mower integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_DEVICE_SN,
    CONF_POLL_INTERVAL,
    DOMAIN,
    POLL_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

class SkMowerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SK-Mower."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            device_sn = user_input[CONF_DEVICE_SN]

            await self.async_set_unique_id(device_sn)
            self._abort_if_unique_id_configured()

            error = await self._async_validate_credentials(user_input)
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=f"SK-Mower {device_sn}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Required(CONF_DEVICE_SN): str,
                    vol.Optional(CONF_POLL_INTERVAL, default=POLL_INTERVAL): int,
                }
            ),
            errors=errors,
        )

    async def _async_validate_credentials(
        self, user_input: dict[str, Any]
    ) -> str | None:
        """Try to authenticate."""
        from .pyskmover.client import _http_request, _OAUTH_BASIC
        from .pyskmover.exceptions import SkMowerError

        def validate():
            return _http_request(
                "POST",
                "/api/auth/oauth/token",
                basic_token=_OAUTH_BASIC,
                form_data={
                    "username": user_input[CONF_USERNAME],
                    "password": user_input[CONF_PASSWORD],
                    "grant_type": "password",
                    "scope": "server",
                },
            )

        try:
            await self.hass.async_add_executor_job(validate)
        except SkMowerError:
            return "invalid_auth"
        except Exception:
            return "unknown"
        return None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SkMowerOptionsFlow:
        """Return the options flow handler."""
        return SkMowerOptionsFlow(config_entry)


class SkMowerOptionsFlow(OptionsFlow):
    """Handle SK-Mower options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_poll = self._config_entry.options.get(
            CONF_POLL_INTERVAL,
            self._config_entry.data.get(CONF_POLL_INTERVAL, POLL_INTERVAL),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_POLL_INTERVAL, default=current_poll): int,
                }
            ),
        )
