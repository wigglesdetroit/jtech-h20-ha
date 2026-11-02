"""Config and options flow."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import NUM_PORTS, JtechMatrix, MatrixError
from .const import CONF_INPUT, CONF_OUTPUT, CONF_TV, DOMAIN, TV_TYPES


class JtechConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for the matrix's address and check it answers like an H20."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input.get(CONF_PORT, 80)
            client = JtechMatrix(host, async_get_clientsession(self.hass), port=port)
            try:
                state = await client.async_get_state()
            except MatrixError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id((state.mac or host).lower())
                self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})
                return self.async_create_entry(
                    title="J-Tech HDMI Matrix",
                    data={CONF_HOST: host, CONF_PORT: port},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_PORT, default=80): vol.All(int, vol.Range(1, 65535)),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return JtechOptionsFlow()


class JtechOptionsFlow(OptionsFlow):
    """Name inputs/outputs (blank hides one) and say which TVs are 4K."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        coordinator = self.config_entry.runtime_data
        tv_selector = SelectSelector(
            SelectSelectorConfig(options=TV_TYPES, mode=SelectSelectorMode.DROPDOWN)
        )
        fields: dict[Any, Any] = {}
        for n in range(1, NUM_PORTS + 1):
            fields[vol.Optional(CONF_INPUT.format(n), default=coordinator.input_name(n))] = str
        for n in range(1, NUM_PORTS + 1):
            fields[vol.Optional(CONF_OUTPUT.format(n), default=coordinator.output_name(n))] = str
            fields[vol.Optional(CONF_TV.format(n), default=coordinator.tv_types()[n])] = tv_selector
        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields))
