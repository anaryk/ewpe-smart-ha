"""Tests for select entity state mapping and command emission."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ewpe_smart.const import (
    PARAM_SUB_ZONE_SWING_LEFT,
    PARAM_SUB_ZONE_SWING_RIGHT,
    PARAM_SUB_ZONE_SWING_UD,
    PARAM_SWING_HORIZONTAL,
    PARAM_SWING_VERTICAL,
    SWING_HORIZONTAL_DEVICE_TO_OPTION,
    SWING_VERTICAL_DEVICE_TO_OPTION,
)
from custom_components.ewpe_smart.select import (
    EwpeSwingSelectEntity,
    supported_select_descriptions,
)


def _make_swing_select(
    status: dict[str, int], param: str = PARAM_SWING_HORIZONTAL
) -> tuple[EwpeSwingSelectEntity, MagicMock]:
    descriptions = supported_select_descriptions(status)
    description = next(d for d in descriptions if d.param == param)

    coordinator = MagicMock()
    coordinator.data = status
    coordinator.last_update_success = True
    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_add_listener = MagicMock(return_value=lambda: None)

    device = MagicMock()
    device.mac = "AA:BB:CC:DD:EE:FF"
    device.name = "Test"
    device.info = {}
    device.set_state = AsyncMock()
    coordinator.device = device

    entity = EwpeSwingSelectEntity(coordinator, description)
    return entity, device


def test_supported_select_descriptions_filters_by_status_keys() -> None:
    data = {"Pow": 1, "SwingLfRig": 1, "SwUpDn": 6}
    descriptions = supported_select_descriptions(data)
    params = {d.param for d in descriptions}
    assert params == {"SwingLfRig", "SwUpDn"}


def test_supported_select_descriptions_excludes_sub_zone_when_unmapped() -> None:
    data = {
        "SwingLfRig": 1,
        "SwUpDn": 6,
        PARAM_SUB_ZONE_SWING_UD: 0,
        PARAM_SUB_ZONE_SWING_RIGHT: 0,
        PARAM_SUB_ZONE_SWING_LEFT: 0,
    }
    descriptions = supported_select_descriptions(data)
    params = {d.param for d in descriptions}
    assert params == {"SwingLfRig", "SwUpDn"}


def test_supported_select_descriptions_includes_sub_zone_when_mapped() -> None:
    data = {
        "SwingLfRig": 1,
        PARAM_SUB_ZONE_SWING_UD: 6,
    }
    descriptions = supported_select_descriptions(data)
    params = {d.param for d in descriptions}
    assert params == {"SwingLfRig", PARAM_SUB_ZONE_SWING_UD}


def test_swing_current_option_maps_device_value() -> None:
    entity, _ = _make_swing_select({"SwingLfRig": 1})
    assert entity.current_option == "full_swing"
    assert set(SWING_HORIZONTAL_DEVICE_TO_OPTION.values()) == {
        "full_swing",
        "left",
        "left_center",
        "center",
        "right_center",
        "right",
    }

    entity_vertical, _ = _make_swing_select({"SwUpDn": 6}, param=PARAM_SWING_VERTICAL)
    assert entity_vertical.current_option == "fixed_lower"
    assert set(SWING_VERTICAL_DEVICE_TO_OPTION.values()) == {
        "full_swing",
        "fixed_upper",
        "fixed_upper_middle",
        "fixed_middle",
        "fixed_lower_middle",
        "fixed_lower",
        "swing_upper",
        "swing_upper_middle",
        "swing_middle",
        "swing_lower_middle",
        "swing_lower",
    }


@pytest.mark.asyncio
async def test_swing_select_option_sends_device_value() -> None:
    entity, device = _make_swing_select({"SwingLfRig": 0})
    await entity.async_select_option("full_swing")
    device.set_state.assert_awaited_once_with({"SwingLfRig": 1})
