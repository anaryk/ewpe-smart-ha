"""Base entity for EWPE Smart."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import EwpeCoordinator


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
