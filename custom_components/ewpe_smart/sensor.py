"""Indoor temperature sensor entity for EWPE Smart."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import PARAM_TEMP_SENSOR
from .coordinator import EwpeConfigEntry, EwpeCoordinator
from .entity import EwpeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EwpeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register the indoor temperature sensor for this config entry."""
    async_add_entities([EwpeIndoorTempSensor(entry.runtime_data)])


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
