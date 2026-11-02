"""Polling coordinator: one /HDMI_MUX.js request every few seconds reads everything."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NUM_PORTS, JtechMatrix, MatrixError, MatrixState
from .const import CONF_INPUT, CONF_OUTPUT, CONF_TV, DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class MatrixCoordinator(DataUpdateCoordinator[MatrixState]):
    """Keeps the latest matrix state."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: JtechMatrix) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> MatrixState:
        try:
            return await self.client.async_get_state()
        except MatrixError as err:
            raise UpdateFailed(str(err)) from err

    # Names and TV types: options first, then the names stored in the matrix.
    def input_name(self, n: int) -> str:
        opt = self.config_entry.options.get(CONF_INPUT.format(n))
        if opt is not None:
            return opt.strip()
        return self.data.input_names.get(n, f"Input{n}") if self.data else f"Input{n}"

    def output_name(self, n: int) -> str:
        opt = self.config_entry.options.get(CONF_OUTPUT.format(n))
        if opt is not None:
            return opt.strip()
        return self.data.output_names.get(n, f"Output{n}") if self.data else f"Output{n}"

    def active_inputs(self) -> list[int]:
        return [n for n in range(1, NUM_PORTS + 1) if self.input_name(n)]

    def active_outputs(self) -> list[int]:
        return [n for n in range(1, NUM_PORTS + 1) if self.output_name(n)]

    def tv_types(self) -> dict[int, str]:
        return {
            n: self.config_entry.options.get(CONF_TV.format(n), "4K")
            for n in range(1, NUM_PORTS + 1)
        }
