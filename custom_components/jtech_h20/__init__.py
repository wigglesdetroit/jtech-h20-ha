"""J-Tech HDMI Matrix (8x8 H20) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import JtechMatrix
from .coordinator import MatrixCoordinator

PLATFORMS = [Platform.SELECT, Platform.SENSOR, Platform.SWITCH]

type MatrixConfigEntry = ConfigEntry[MatrixCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: MatrixConfigEntry) -> bool:
    client = JtechMatrix(
        entry.data[CONF_HOST],
        async_get_clientsession(hass),
        port=entry.data.get(CONF_PORT, 80),
    )
    coordinator = MatrixCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: MatrixConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: MatrixConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
