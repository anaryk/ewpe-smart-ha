"""Tests for switch entity state mapping and command emission."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ewpe_smart.const import (
    PARAM_LIG,
    PARAM_QUIET,
    PARAM_SLEEP,
    PARAM_SLEEP_MODE,
)
from custom_components.ewpe_smart.switch import (
    EwpeSwitchEntity,
    supported_switch_descriptions,
)


def _make_switch(
    status: dict[str, int], param: str = PARAM_QUIET
) -> tuple[EwpeSwitchEntity, MagicMock]:
    descriptions = supported_switch_descriptions(status)
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

    entity = EwpeSwitchEntity(coordinator, description)
    return entity, device


def test_supported_switch_descriptions_filters_by_status_keys() -> None:
    data = {"Pow": 1, "Quiet": 0, "Lig": 1}
    descriptions = supported_switch_descriptions(data)
    params = {d.param for d in descriptions}
    assert params == {PARAM_QUIET, PARAM_LIG}


def test_is_on_reflects_param_value() -> None:
    entity, _ = _make_switch({"Quiet": 1})
    assert entity.is_on is True

    entity_off, _ = _make_switch({"Quiet": 0})
    assert entity_off.is_on is False


@pytest.mark.asyncio
async def test_turn_on_sends_param_one() -> None:
    entity, device = _make_switch({"Lig": 0}, param=PARAM_LIG)
    await entity.async_turn_on()
    device.set_state.assert_awaited_once_with({PARAM_LIG: 1})


@pytest.mark.asyncio
async def test_quiet_turns_on_with_two_like_the_app() -> None:
    entity, device = _make_switch({"Quiet": 0})
    await entity.async_turn_on()
    device.set_state.assert_awaited_once_with({PARAM_QUIET: 2})
    await entity.async_turn_off()
    device.set_state.assert_awaited_with({PARAM_QUIET: 0})


@pytest.mark.parametrize("value", [1, 2, 3])
def test_quiet_reads_any_non_zero_value_as_on(value: int) -> None:
    entity, _ = _make_switch({"Quiet": value})
    assert entity.is_on is True


@pytest.mark.asyncio
async def test_turn_off_sends_param_zero() -> None:
    entity, device = _make_switch({"Lig": 1}, param=PARAM_LIG)
    await entity.async_turn_off()
    device.set_state.assert_awaited_once_with({PARAM_LIG: 0})


@pytest.mark.asyncio
async def test_sleep_also_writes_sleep_mode() -> None:
    entity, device = _make_switch({"SwhSlp": 0}, param=PARAM_SLEEP)
    await entity.async_turn_on()
    device.set_state.assert_awaited_once_with({PARAM_SLEEP: 1, PARAM_SLEEP_MODE: 1})
