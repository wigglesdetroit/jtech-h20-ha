"""Switches for EDID flags per input: HDR, 3D, and deep color (deep color off by default)."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MatrixConfigEntry
from .api import MatrixError
from .entity import MatrixEntity

FLAGS = [
    ("hdr", "HDR", "mdi:hdr", True),
    ("three_d", "3D", "mdi:video-3d", True),
    ("bit30", "30-bit color", "mdi:palette", False),
    ("bit36", "36-bit color", "mdi:palette", False),
    ("bit48", "48-bit color", "mdi:palette", False),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MatrixConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    c = entry.runtime_data
    async_add_entities(EdidFlagSwitch(c, i, *flag) for i in c.active_inputs() for flag in FLAGS)


class EdidFlagSwitch(MatrixEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator, input_no: int, field: str, label: str, icon: str, default_on: bool
    ) -> None:
        super().__init__(coordinator, f"input_{input_no}_{field}")
        self._in = input_no
        self._field = field
        self._attr_name = f"{coordinator.input_name(input_no)} {label}"
        self._attr_icon = icon
        self._attr_entity_registry_enabled_default = default_on

    @property
    def is_on(self) -> bool | None:
        edid = self.coordinator.data.edid.get(self._in)
        return getattr(edid, self._field) if edid else None

    async def _set(self, value: bool) -> None:
        try:
            await self.coordinator.client.async_update_edid(self._in, **{self._field: value})
        except MatrixError as err:
            raise HomeAssistantError(str(err)) from err
        await self._after_write()

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)
