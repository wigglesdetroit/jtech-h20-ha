"""Selects: source per TV output, EDID video mode and audio per input."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MatrixConfigEntry
from .api import AUDIO_MODES, VIDEO_MODES, MatrixError
from .entity import MatrixEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MatrixConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    c = entry.runtime_data
    entities: list[SelectEntity] = [OutputSourceSelect(c, o) for o in c.active_outputs()]
    for i in c.active_inputs():
        entities += [EdidVideoSelect(c, i), EdidAudioSelect(c, i)]
    async_add_entities(entities)


class OutputSourceSelect(MatrixEntity, SelectEntity):
    """Which input a TV output shows."""

    _attr_icon = "mdi:video-input-hdmi"

    def __init__(self, coordinator, output_no: int) -> None:
        super().__init__(coordinator, f"output_{output_no}_source")
        self._out = output_no
        self._attr_name = f"{coordinator.output_name(output_no)} source"

    def _names(self) -> dict[int, str]:
        return {i: self.coordinator.input_name(i) for i in self.coordinator.active_inputs()}

    @property
    def options(self) -> list[str]:
        return list(self._names().values())

    @property
    def current_option(self) -> str | None:
        return self._names().get(self.coordinator.data.routing.get(self._out))

    @property
    def extra_state_attributes(self) -> dict:
        state = self.coordinator.data
        inp = state.routing.get(self._out)
        active = set(self.coordinator.active_outputs())
        shared = [
            self.coordinator.output_name(o)
            for o in state.outputs_on_input(inp)
            if o != self._out and o in active
        ]
        return {"output": self._out, "input": inp, "shared_with": shared}

    async def async_select_option(self, option: str) -> None:
        target = next((i for i, n in self._names().items() if n == option), None)
        if target is None:
            raise HomeAssistantError(f"Unknown source {option}")
        try:
            await self.coordinator.client.async_route(self._out, target)
        except MatrixError as err:
            raise HomeAssistantError(str(err)) from err
        await self._after_write()


class _EdidSelect(MatrixEntity, SelectEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _field: str
    _choices: dict[str, str]

    def __init__(self, coordinator, input_no: int, key: str, label: str) -> None:
        super().__init__(coordinator, f"input_{input_no}_{key}")
        self._in = input_no
        self._attr_name = f"{coordinator.input_name(input_no)} {label}"

    @property
    def options(self) -> list[str]:
        return list(self._choices.values())

    @property
    def current_option(self) -> str | None:
        edid = self.coordinator.data.edid.get(self._in)
        return self._choices.get(getattr(edid, self._field)) if edid else None

    async def async_select_option(self, option: str) -> None:
        code = next((k for k, v in self._choices.items() if v == option), None)
        if code is None:
            raise HomeAssistantError(f"Unknown option {option}")
        try:
            await self.coordinator.client.async_update_edid(self._in, **{self._field: code})
        except MatrixError as err:
            raise HomeAssistantError(str(err)) from err
        await self._after_write()


class EdidVideoSelect(_EdidSelect):
    _attr_icon = "mdi:monitor-screenshot"
    _field = "mode"
    _choices = VIDEO_MODES

    def __init__(self, coordinator, input_no: int) -> None:
        super().__init__(coordinator, input_no, "edid_video", "video (EDID)")


class EdidAudioSelect(_EdidSelect):
    _attr_icon = "mdi:surround-sound"
    _field = "audio"
    _choices = AUDIO_MODES

    def __init__(self, coordinator, input_no: int) -> None:
        super().__init__(coordinator, input_no, "edid_audio", "audio (EDID)")
