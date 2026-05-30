"""Switch entities for EWPE Smart auxiliary features."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MANUFACTURER,
    PARAM_AIR,
    PARAM_BLO,
    PARAM_HEALTH,
    PARAM_LIG,
    PARAM_QUIET,
    PARAM_SLEEP,
    PARAM_SVST,
    PARAM_TUR,
    POWER_OFF,
    POWER_ON,
)
from .coordinator import EwpeCoordinator


@dataclass(frozen=True, kw_only=True)
class EwpeSwitchDescription:
    """Maps a switch entity to a Gree protocol parameter."""

    param: str
    unique_id_suffix: str
    translation_key: str


SWITCH_DESCRIPTIONS: tuple[EwpeSwitchDescription, ...] = (
    EwpeSwitchDescription(
        param=PARAM_SLEEP, unique_id_suffix="sleep", translation_key="sleep"
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
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register switch entities supported by this device."""
    coordinator: EwpeCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}
    async_add_entities(
        EwpeSwitchEntity(coordinator, entry, description)
        for description in supported_switch_descriptions(data)
    )


class EwpeSwitchEntity(CoordinatorEntity[EwpeCoordinator], SwitchEntity):
    """Binary switch backed by a single Gree protocol parameter."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EwpeCoordinator,
        entry: ConfigEntry,
        description: EwpeSwitchDescription,
    ) -> None:
        super().__init__(coordinator)
        self._description = description
        device = coordinator.device
        self._attr_translation_key = description.translation_key
        self._attr_unique_id = f"{device.mac}_{description.unique_id_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.mac or entry.entry_id)},
            name=device.name or entry.title,
            manufacturer=MANUFACTURER,
            model=device.info.get("model") if device.info else None,
            sw_version=device.info.get("ver") if device.info else None,
        )

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
        await self.coordinator.device.set_state({self._description.param: value})
        await self.coordinator.async_request_refresh()
