"""Sensor entities for EWPE Smart."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfFrequency,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import PARAM_TEMP_SENSOR
from .coordinator import EwpeConfigEntry, EwpeCoordinator
from .entity import EwpeEntity
from .params_catalog import (
    EXTRA_SENSOR_DESCRIPTIONS,
    TEMP_OFFSET_PARAMS,
    SensorDescriptionRef,
    diagnostic_params,
    param_disabled_by_default,
)

_DEVICE_CLASS = {
    "temperature": SensorDeviceClass.TEMPERATURE,
    "humidity": SensorDeviceClass.HUMIDITY,
    "pm25": SensorDeviceClass.PM25,
}

_STATE_CLASS = {
    "measurement": SensorStateClass.MEASUREMENT,
}

_ENTITY_CATEGORY = {
    "diagnostic": EntityCategory.DIAGNOSTIC,
}

_UNIT = {
    "°C": UnitOfTemperature.CELSIUS,
    "%": PERCENTAGE,
    "µg/m³": "µg/m³",
    "Hz": UnitOfFrequency.HERTZ,
}


_INVALID_MAC = frozenset({"", "0", "00:00:00:00:00:00", "000000000000"})


def is_valid_status_mac(value: Any) -> bool:
    """True when a status-reported ``mac`` col is usable (not a placeholder)."""
    if value is None:
        return False
    return str(value).strip().casefold() not in _INVALID_MAC


def supported_extra_sensor_descriptions(
    data: dict[str, Any],
) -> tuple[SensorDescriptionRef, ...]:
    """Return explicit sensor descriptions whose param appeared in a status reply."""
    return tuple(
        desc
        for desc in EXTRA_SENSOR_DESCRIPTIONS
        if desc.param in data
        and (desc.param != "mac" or is_valid_status_mac(data[desc.param]))
    )


def _slugify_param(param: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", param).strip("_").lower()
    return slug or "param"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EwpeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    data = coordinator.data or {}
    entities: list[SensorEntity] = [EwpeIndoorTempSensor(coordinator)]
    entities.extend(
        EwpeExtraSensor(coordinator, description)
        for description in supported_extra_sensor_descriptions(data)
    )
    entities.extend(
        EwpeDiagnosticSensor(coordinator, param) for param in diagnostic_params(data)
    )
    async_add_entities(entities)


class EwpeIndoorTempSensor(EwpeEntity, SensorEntity):
    """Reports the indoor temperature reading from the unit's TemSen sensor."""

    _attr_translation_key = "indoor_temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: EwpeCoordinator) -> None:
        super().__init__(coordinator, "indoor_temperature")

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data or {}
        value = data.get(PARAM_TEMP_SENSOR)
        if value is None or not -10 <= value <= 60:
            return None
        return float(value)


class EwpeExtraSensor(EwpeEntity, SensorEntity):
    """Named sensors mapped from the parameter catalog."""

    def __init__(
        self,
        coordinator: EwpeCoordinator,
        description: SensorDescriptionRef,
    ) -> None:
        super().__init__(coordinator, description.unique_id_suffix)
        self._description = description
        self._attr_translation_key = description.translation_key
        if description.device_class:
            self._attr_device_class = _DEVICE_CLASS.get(description.device_class)
        if description.value_kind == "text":
            self._attr_state_class = None
        elif description.state_class:
            self._attr_state_class = _STATE_CLASS.get(description.state_class)
        if description.entity_category:
            self._attr_entity_category = _ENTITY_CATEGORY.get(
                description.entity_category
            )
        if description.native_unit_of_measurement:
            unit = description.native_unit_of_measurement
            self._attr_native_unit_of_measurement = _UNIT.get(unit, unit)
        if param_disabled_by_default(description.param):
            self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> float | int | str | None:
        value = (self.coordinator.data or {}).get(self._description.param)
        if value is None:
            return None
        if self._description.value_kind == "text":
            if isinstance(value, (list, dict)):
                return str(value)
            return str(value)
        if isinstance(value, (list, dict)):
            return str(value)
        param = self._description.param
        if param in TEMP_OFFSET_PARAMS and param != PARAM_TEMP_SENSOR:
            if not -40 <= value <= 60:
                return None
            return float(value)
        if self._description.percent_range:
            if not 0 <= value <= 100:
                return None
            return float(value)
        if self._description.device_class == "temperature":
            if not -40 <= value <= 60:
                return None
            return float(value)
        return int(value)


class EwpeDiagnosticSensor(EwpeEntity, SensorEntity):
    """Read-only fallback for wire params without an explicit entity mapping."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: EwpeCoordinator,
        param: str,
    ) -> None:
        super().__init__(coordinator, f"raw_{_slugify_param(param)}")
        self._param = param
        self._attr_name = param
        self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> int | None:
        value = (self.coordinator.data or {}).get(self._param)
        if value is None:
            return None
        return int(value)
