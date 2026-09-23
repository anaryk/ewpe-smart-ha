"""Binary sensor entities for EWPE Smart."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import EwpeConfigEntry, EwpeCoordinator
from .entity import EwpeEntity
from .params_catalog import (
    BINARY_SENSOR_DESCRIPTIONS,
    BinarySensorDescriptionRef,
    param_disabled_by_default,
)

_DEVICE_CLASS = {
    "problem": BinarySensorDeviceClass.PROBLEM,
    "motion": BinarySensorDeviceClass.MOTION,
    "running": BinarySensorDeviceClass.RUNNING,
}


def supported_binary_sensor_descriptions(
    data: dict[str, int],
) -> tuple[BinarySensorDescriptionRef, ...]:
    """Return binary sensor descriptions whose param appeared in a status reply."""
    return tuple(desc for desc in BINARY_SENSOR_DESCRIPTIONS if desc.param in data)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EwpeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    data = coordinator.data or {}
    async_add_entities(
        EwpeBinarySensor(coordinator, description)
        for description in supported_binary_sensor_descriptions(data)
    )


class EwpeBinarySensor(EwpeEntity, BinarySensorEntity):
    """Binary sensor backed by a Gree protocol parameter."""

    def __init__(
        self,
        coordinator: EwpeCoordinator,
        description: BinarySensorDescriptionRef,
    ) -> None:
        super().__init__(coordinator, description.unique_id_suffix)
        self._description = description
        self._attr_translation_key = description.translation_key
        if description.device_class:
            self._attr_device_class = _DEVICE_CLASS.get(description.device_class)
        if param_disabled_by_default(description.param):
            self._attr_entity_registry_enabled_default = False

    @property
    def is_on(self) -> bool | None:
        value = (self.coordinator.data or {}).get(self._description.param)
        if value is None:
            return None
        return bool(value)
