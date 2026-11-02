"""Base entity."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import MatrixCoordinator


class MatrixEntity(CoordinatorEntity[MatrixCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: MatrixCoordinator, key: str) -> None:
        super().__init__(coordinator)
        uid = coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        self._attr_unique_id = f"{uid}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, uid)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name="HDMI Matrix",
            configuration_url=coordinator.client.base_url,
        )

    async def _after_write(self) -> None:
        # Refresh right away (not debounced) so the UI shows what the matrix now reports.
        await self.coordinator.async_refresh()
