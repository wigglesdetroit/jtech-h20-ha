"""Sensors: what resolution and audio each TV output is getting."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MatrixConfigEntry
from .api import resolution_for_output
from .entity import MatrixEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MatrixConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    c = entry.runtime_data
    async_add_entities(OutputVideoSensor(c, o) for o in c.active_outputs())


class OutputVideoSensor(MatrixEntity, SensorEntity):
    """Best-known resolution reaching a TV, worked out from its input's EDID setting."""

    _attr_icon = "mdi:television-guide"

    def __init__(self, coordinator, output_no: int) -> None:
        super().__init__(coordinator, f"output_{output_no}_video")
        self._out = output_no
        self._attr_name = f"{coordinator.output_name(output_no)} video"

    @property
    def native_value(self) -> str | None:
        return resolution_for_output(self.coordinator.data, self._out, self.coordinator.tv_types())

    @property
    def extra_state_attributes(self) -> dict:
        state = self.coordinator.data
        inp = state.routing.get(self._out)
        edid = state.edid.get(inp)
        tv = self.coordinator.tv_types()
        held_back_by = None
        if edid and edid.mode == "1" and tv.get(self._out) == "4K":
            held_back_by = "input EDID fixed at 1080p"
        return {
            "source": self.coordinator.input_name(inp) or f"Input{inp}",
            "input": inp,
            "edid_video": edid.mode_name if edid else None,
            "edid_audio": edid.audio_name if edid else None,
            "hdr": edid.hdr if edid else None,
            "tv_supports": tv.get(self._out),
            "held_back_by": held_back_by,
            "basis": "matrix EDID setting (the matrix does not report live signal)",
        }
