"""Number entities for EWPE Smart timers and sleep curve."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import EwpeConfigEntry, EwpeCoordinator
from .entity import EwpeEntity
from .params_catalog import (
    NUMBER_DESCRIPTIONS,
    NumberDescriptionRef,
    param_disabled_by_default,
)

_MODE = {
    "auto": NumberMode.AUTO,
    "box": NumberMode.BOX,
    "slider": NumberMode.SLIDER,
}

_UNIT = {
    "min": UnitOfTime.MINUTES,
    "°C": UnitOfTemperature.CELSIUS,
}


def supported_number_descriptions(
    data: dict[str, int],
) -> tuple[NumberDescriptionRef, ...]:
    """Return number descriptions whose param appeared in a status reply."""
    return tuple(desc for desc in NUMBER_DESCRIPTIONS if desc.param in data)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EwpeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    data = coordinator.data or {}
    async_add_entities(
        EwpeNumberEntity(coordinator, description)
        for description in supported_number_descriptions(data)
    )


class EwpeNumberEntity(EwpeEntity, NumberEntity):
    """Numeric parameter backed by a Gree protocol key."""

    def __init__(
        self,
        coordinator: EwpeCoordinator,
        description: NumberDescriptionRef,
    ) -> None:
        super().__init__(coordinator, description.unique_id_suffix)
        self._description = description
        self._attr_translation_key = description.translation_key
        self._attr_native_min_value = description.native_min_value
        self._attr_native_max_value = description.native_max_value
        self._attr_native_step = description.native_step
        self._attr_mode = _MODE.get(description.mode, NumberMode.AUTO)
        if description.native_unit_of_measurement:
            unit = description.native_unit_of_measurement
            self._attr_native_unit_of_measurement = _UNIT.get(unit, unit)
        if param_disabled_by_default(description.param):
            self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> float | None:
        value = (self.coordinator.data or {}).get(self._description.param)
        if value is None:
            return None
        return float(value)

    async def async_set_native_value(self, value: float) -> None:
        await self._send_params({self._description.param: int(round(value))})
