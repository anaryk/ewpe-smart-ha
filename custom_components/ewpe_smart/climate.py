"""Climate entity for EWPE Smart air conditioners."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    FAN_SPEED_AUTO,
    FAN_SPEED_HIGH,
    FAN_SPEED_LOW,
    FAN_SPEED_MEDIUM,
    FAN_SPEED_MEDIUM_HIGH,
    FAN_SPEED_MEDIUM_LOW,
    MAX_TEMP,
    MIN_TEMP,
    MODE_AUTO,
    MODE_COOL,
    MODE_DRY,
    MODE_FAN,
    MODE_HEAT,
    PARAM_FAN_SPEED,
    PARAM_MODE,
    PARAM_POWER,
    PARAM_QUIET,
    PARAM_SET_TEMP,
    PARAM_TEMP_SENSOR,
    PARAM_TUR,
    POWER_OFF,
    POWER_ON,
    QUIET_MODE_ON,
)
from .coordinator import EwpeConfigEntry, EwpeCoordinator
from .device import EwpeError
from .entity import EwpeEntity

HVAC_MODE_TO_DEVICE: dict[HVACMode, int] = {
    HVACMode.AUTO: MODE_AUTO,
    HVACMode.COOL: MODE_COOL,
    HVACMode.DRY: MODE_DRY,
    HVACMode.FAN_ONLY: MODE_FAN,
    HVACMode.HEAT: MODE_HEAT,
}
DEVICE_TO_HVAC_MODE: dict[int, HVACMode] = {
    v: k for k, v in HVAC_MODE_TO_DEVICE.items()
}

# The unit has five fixed steps; HA only names four of them, so steps 2 and 4
# use custom modes translated in strings.json.
FAN_MEDIUM_LOW = "medium_low"
FAN_MEDIUM_HIGH = "medium_high"

FAN_MODE_TO_DEVICE: dict[str, int] = {
    FAN_AUTO: FAN_SPEED_AUTO,
    FAN_LOW: FAN_SPEED_LOW,
    FAN_MEDIUM_LOW: FAN_SPEED_MEDIUM_LOW,
    FAN_MEDIUM: FAN_SPEED_MEDIUM,
    FAN_MEDIUM_HIGH: FAN_SPEED_MEDIUM_HIGH,
    FAN_HIGH: FAN_SPEED_HIGH,
}
DEVICE_TO_FAN_MODE: dict[int, str] = {v: k for k, v in FAN_MODE_TO_DEVICE.items()}


SERVICE_SET_STATE = "set_state"
ATTR_FAN_MODE = "fan_mode"
ATTR_QUIET = "quiet"
ATTR_TURBO = "turbo"

# The unit beeps once per command, so this service writes any combination of
# mode, target, fan, quiet and turbo in a single packet.
SET_STATE_SCHEMA = vol.All(
    cv.has_at_least_one_key(
        ATTR_HVAC_MODE, ATTR_TEMPERATURE, ATTR_FAN_MODE, ATTR_QUIET, ATTR_TURBO
    ),
    cv.make_entity_service_schema(
        {
            vol.Optional(ATTR_HVAC_MODE): vol.Coerce(HVACMode),
            vol.Optional(ATTR_TEMPERATURE): vol.Coerce(float),
            vol.Optional(ATTR_FAN_MODE): cv.string,
            vol.Optional(ATTR_QUIET): cv.boolean,
            vol.Optional(ATTR_TURBO): cv.boolean,
        }
    ),
)


def _hvac_mode_params(hvac_mode: HVACMode) -> dict[str, int]:
    if hvac_mode == HVACMode.OFF:
        return {PARAM_POWER: POWER_OFF}
    device_mode = HVAC_MODE_TO_DEVICE.get(hvac_mode)
    if device_mode is None:
        raise ValueError(f"Unsupported hvac_mode: {hvac_mode}")
    return {PARAM_POWER: POWER_ON, PARAM_MODE: device_mode}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EwpeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register the climate entity for this config entry."""
    async_add_entities([EwpeClimateEntity(entry.runtime_data)])
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SET_STATE, SET_STATE_SCHEMA, "async_set_state"
    )


class EwpeClimateEntity(EwpeEntity, ClimateEntity):
    """Climate entity backed by an :class:`EwpeDevice`."""

    _attr_name = None
    _attr_translation_key = "ewpe"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.AUTO,
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
    ]
    _attr_fan_modes = list(FAN_MODE_TO_DEVICE)
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: EwpeCoordinator) -> None:
        super().__init__(coordinator, "climate")

    @property
    def _data(self) -> dict[str, int]:
        return self.coordinator.data or {}

    @property
    def hvac_mode(self) -> HVACMode | None:
        if self._data.get(PARAM_POWER) == POWER_OFF:
            return HVACMode.OFF
        mode = self._data.get(PARAM_MODE)
        if mode is None:
            return None
        return DEVICE_TO_HVAC_MODE.get(mode)

    @property
    def fan_mode(self) -> str | None:
        speed = self._data.get(PARAM_FAN_SPEED)
        if speed is None:
            return None
        return DEVICE_TO_FAN_MODE.get(speed)

    @property
    def target_temperature(self) -> float | None:
        value = self._data.get(PARAM_SET_TEMP)
        return float(value) if value is not None else None

    @property
    def current_temperature(self) -> float | None:
        value = self._data.get(PARAM_TEMP_SENSOR)
        if value is None:
            return None
        if not -10 <= value <= 60:
            return None
        return float(value)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self._send(_hvac_mode_params(hvac_mode))

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        device_speed = FAN_MODE_TO_DEVICE.get(fan_mode)
        if device_speed is None:
            raise ValueError(f"Unsupported fan_mode: {fan_mode}")
        await self._send({PARAM_FAN_SPEED: device_speed})

    async def async_set_temperature(self, **kwargs: Any) -> None:
        # climate.set_temperature may carry hvac_mode; send both in one packet
        # because the unit beeps once per command.
        params: dict[str, int] = {}
        if (hvac_mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            params.update(_hvac_mode_params(hvac_mode))
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            params[PARAM_SET_TEMP] = int(round(float(temperature)))
        if params:
            await self._send(params)

    async def async_set_state(self, **kwargs: Any) -> None:
        """Write every given setting in one packet."""
        params: dict[str, int] = {}
        if (hvac_mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            if hvac_mode not in self.hvac_modes:
                raise self._invalid("unsupported_hvac_mode", hvac_mode=hvac_mode)
            params.update(_hvac_mode_params(hvac_mode))
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            if not self.min_temp <= temperature <= self.max_temp:
                raise self._invalid(
                    "temperature_out_of_range",
                    temperature=str(temperature),
                    min_temp=str(self.min_temp),
                    max_temp=str(self.max_temp),
                )
            params[PARAM_SET_TEMP] = int(round(temperature))
        if (fan_mode := kwargs.get(ATTR_FAN_MODE)) is not None:
            if fan_mode not in FAN_MODE_TO_DEVICE:
                raise self._invalid("unsupported_fan_mode", fan_mode=fan_mode)
            params[PARAM_FAN_SPEED] = FAN_MODE_TO_DEVICE[fan_mode]
        for attr, param, on_value in (
            (ATTR_QUIET, PARAM_QUIET, QUIET_MODE_ON),
            (ATTR_TURBO, PARAM_TUR, POWER_ON),
        ):
            if (enabled := kwargs.get(attr)) is None:
                continue
            if param not in self._data:
                raise self._invalid("not_supported_by_device", setting=attr)
            params[param] = on_value if enabled else POWER_OFF
        await self._send(params)

    def _invalid(self, key: str, **placeholders: str) -> ServiceValidationError:
        return ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key=key,
            translation_placeholders=placeholders,
        )

    async def async_turn_on(self) -> None:
        await self._send({PARAM_POWER: POWER_ON})

    async def async_turn_off(self) -> None:
        await self._send({PARAM_POWER: POWER_OFF})

    async def _send(self, params: dict[str, int]) -> None:
        try:
            await self.coordinator.device.set_state(params)
        except EwpeError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await self.coordinator.async_request_refresh()
