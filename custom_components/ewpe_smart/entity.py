"""Base entity for EWPE Smart."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import EwpeCoordinator
from .device import EwpeError


class EwpeEntity(CoordinatorEntity[EwpeCoordinator]):
    """Common device info and unique ID handling."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EwpeCoordinator, key: str) -> None:
        super().__init__(coordinator)
        device = coordinator.device
        self._attr_unique_id = f"{device.mac}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device.mac))},
            name=device.name,
            manufacturer=MANUFACTURER,
            model=device.info.get("model"),
            sw_version=device.info.get("ver"),
        )

    async def _send_params(self, params: dict[str, int]) -> None:
        """Write ``params`` in one packet, then refresh."""
        try:
            await self.coordinator.device.set_state(params)
        except EwpeError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await self.coordinator.async_request_refresh()
