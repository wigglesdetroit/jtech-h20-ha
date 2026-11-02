"""Diagnostics download: the matrix state as the integration sees it."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from . import MatrixConfigEntry

TO_REDACT = {CONF_HOST, "mac", "unique_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MatrixConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    state = coordinator.data
    return {
        "entry": async_redact_data(
            {
                "data": dict(entry.data),
                "options": dict(entry.options),
                "unique_id": entry.unique_id,
            },
            TO_REDACT,
        ),
        "last_update_success": coordinator.last_update_success,
        "state": async_redact_data(asdict(state), TO_REDACT) if state else None,
        "raw_edid": {n: e.encode() for n, e in state.edid.items()} if state else None,
    }
