"""Switch entities for EWPE Smart auxiliary features."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    PARAM_AIR,
    PARAM_BLO,
    PARAM_HEALTH,
    PARAM_LIG,
    PARAM_QUIET,
    PARAM_SLEEP,
    PARAM_SLEEP_MODE,
    PARAM_SVST,
    PARAM_TUR,
    POWER_OFF,
    POWER_ON,
)
from .coordinator import EwpeConfigEntry, EwpeCoordinator
from .entity import EwpeEntity


@dataclass(frozen=True, kw_only=True)
class EwpeSwitchDescription:
    """Maps a switch entity to a Gree protocol parameter."""

    param: str
    unique_id_suffix: str
    translation_key: str
    # Params written alongside ``param``, but never read back.
    also_writes: tuple[str, ...] = ()


SWITCH_DESCRIPTIONS: tuple[EwpeSwitchDescription, ...] = (
    EwpeSwitchDescription(
        param=PARAM_SLEEP,
        unique_id_suffix="sleep",
        translation_key="sleep",
        also_writes=(PARAM_SLEEP_MODE,),
    ),
    EwpeSwitchDescription(
        param=PARAM_TUR, unique_id_suffix="turbo", translation_key="turbo"
    ),
    EwpeSwitchDescription(
        param=PARAM_QUIET, unique_id_suffix="quiet", translation_key="quiet"
    ),
    EwpeSwitchDescription(
        param=PARAM_BLO, unique_id_suffix="xfan", translation_key="xfan"
    ),
    EwpeSwitchDescription(
        param=PARAM_HEALTH, unique_id_suffix="health", translation_key="health"
    ),
    EwpeSwitchDescription(
        param=PARAM_LIG,
        unique_id_suffix="display_light",
        translation_key="display_light",
    ),
    EwpeSwitchDescription(
        param=PARAM_SVST,
        unique_id_suffix="energy_save",
        translation_key="energy_save",
    ),
    EwpeSwitchDescription(
        param=PARAM_AIR, unique_id_suffix="fresh_air", translation_key="fresh_air"
    ),
)


def supported_switch_descriptions(
    data: Mapping[str, int],
) -> tuple[EwpeSwitchDescription, ...]:
    """Return switch descriptions whose param appeared in a status reply."""
    return tuple(desc for desc in SWITCH_DESCRIPTIONS if desc.param in data)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EwpeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register switch entities supported by this device."""
    coordinator = entry.runtime_data
    async_add_entities(
        EwpeSwitchEntity(coordinator, description)
        for description in supported_switch_descriptions(coordinator.data or {})
    )


class EwpeSwitchEntity(EwpeEntity, SwitchEntity):
    """Binary switch backed by a single Gree protocol parameter."""

    def __init__(
        self,
        coordinator: EwpeCoordinator,
        description: EwpeSwitchDescription,
    ) -> None:
        super().__init__(coordinator, description.unique_id_suffix)
        self._description = description
        self._attr_translation_key = description.translation_key

    @property
    def is_on(self) -> bool | None:
        value = (self.coordinator.data or {}).get(self._description.param)
        if value is None:
            return None
        return bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send(POWER_ON)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send(POWER_OFF)

    async def _send(self, value: int) -> None:
        params = {self._description.param: value}
        params.update(dict.fromkeys(self._description.also_writes, value))
        await self.coordinator.device.set_state(params)
        await self.coordinator.async_request_refresh()
