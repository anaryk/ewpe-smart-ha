"""Select entities for EWPE Smart."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    PARAM_SUB_ZONE_SWING_LEFT,
    PARAM_SUB_ZONE_SWING_RIGHT,
    PARAM_SUB_ZONE_SWING_UD,
    PARAM_SWING_HORIZONTAL,
    PARAM_SWING_VERTICAL,
    SWING_HORIZONTAL_DEVICE_TO_OPTION,
    SWING_VERTICAL_DEVICE_TO_OPTION,
)
from .coordinator import EwpeConfigEntry, EwpeCoordinator
from .entity import EwpeEntity
from .params_catalog import param_disabled_by_default


@dataclass(frozen=True, kw_only=True)
class EwpeSelectDescription:
    """Maps a select entity to a Gree protocol parameter."""

    param: str
    unique_id_suffix: str
    translation_key: str
    device_to_option: dict[int, str]


_SUB_ZONE_SWING_PARAMS = frozenset(
    {
        PARAM_SUB_ZONE_SWING_UD,
        PARAM_SUB_ZONE_SWING_RIGHT,
        PARAM_SUB_ZONE_SWING_LEFT,
    }
)


def _select_param_supported(
    description: EwpeSelectDescription, data: Mapping[str, int]
) -> bool:
    """Whether a swing select should be created for this status snapshot."""
    if description.param not in data:
        return False
    if description.param not in _SUB_ZONE_SWING_PARAMS:
        return True
    value = data[description.param]
    if value is None:
        return False
    return int(value) in description.device_to_option


SELECT_DESCRIPTIONS: tuple[EwpeSelectDescription, ...] = (
    EwpeSelectDescription(
        param=PARAM_SWING_HORIZONTAL,
        unique_id_suffix="swing_horizontal",
        translation_key="swing_horizontal",
        device_to_option=SWING_HORIZONTAL_DEVICE_TO_OPTION,
    ),
    EwpeSelectDescription(
        param=PARAM_SWING_VERTICAL,
        unique_id_suffix="swing_vertical",
        translation_key="swing_vertical",
        device_to_option=SWING_VERTICAL_DEVICE_TO_OPTION,
    ),
    EwpeSelectDescription(
        param=PARAM_SUB_ZONE_SWING_UD,
        unique_id_suffix="sub_zone_swing_ud",
        translation_key="sub_zone_swing_ud",
        device_to_option=SWING_VERTICAL_DEVICE_TO_OPTION,
    ),
    EwpeSelectDescription(
        param=PARAM_SUB_ZONE_SWING_RIGHT,
        unique_id_suffix="sub_zone_swing_right_lr",
        translation_key="sub_zone_swing_right_lr",
        device_to_option=SWING_HORIZONTAL_DEVICE_TO_OPTION,
    ),
    EwpeSelectDescription(
        param=PARAM_SUB_ZONE_SWING_LEFT,
        unique_id_suffix="sub_zone_swing_left_lr",
        translation_key="sub_zone_swing_left_lr",
        device_to_option=SWING_HORIZONTAL_DEVICE_TO_OPTION,
    ),
)


def supported_select_descriptions(
    data: Mapping[str, int],
) -> tuple[EwpeSelectDescription, ...]:
    """Return swing selects supported by this device snapshot."""
    return tuple(
        desc for desc in SELECT_DESCRIPTIONS if _select_param_supported(desc, data)
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EwpeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register select entities supported by this device."""
    coordinator = entry.runtime_data
    data = coordinator.data or {}
    async_add_entities(
        EwpeSwingSelectEntity(coordinator, description)
        for description in supported_select_descriptions(data)
    )


class EwpeSwingSelectEntity(EwpeEntity, SelectEntity):
    """Swing mode select backed by a single Gree protocol parameter."""

    def __init__(
        self,
        coordinator: EwpeCoordinator,
        description: EwpeSelectDescription,
    ) -> None:
        super().__init__(coordinator, description.unique_id_suffix)
        self._description = description
        self._option_to_device = {
            label: value for value, label in description.device_to_option.items()
        }
        self._attr_translation_key = description.translation_key
        self._attr_options = list(description.device_to_option.values())
        if param_disabled_by_default(description.param):
            self._attr_entity_registry_enabled_default = False

    @property
    def current_option(self) -> str | None:
        value = (self.coordinator.data or {}).get(self._description.param)
        if value is None:
            return None
        return self._description.device_to_option.get(int(value))

    async def async_select_option(self, option: str) -> None:
        device_value = self._option_to_device.get(option)
        if device_value is None:
            raise ValueError(f"Unsupported option: {option}")
        await self._send_params({self._description.param: device_value})
