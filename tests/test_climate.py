"""Tests for the climate entity state mapping and command emission."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    HVACMode,
)
from homeassistant.exceptions import HomeAssistantError

from custom_components.ewpe_smart.climate import EwpeClimateEntity
from custom_components.ewpe_smart.const import (
    PARAM_FAN_SPEED,
    PARAM_MODE,
    PARAM_POWER,
    PARAM_SET_TEMP,
)
from custom_components.ewpe_smart.protocol import EwpeTimeout


def _make_entity(status: dict[str, int]) -> tuple[EwpeClimateEntity, MagicMock]:
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

    entity = EwpeClimateEntity(coordinator)
    return entity, device


def test_power_off_maps_to_hvac_off() -> None:
    entity, _ = _make_entity({"Pow": 0, "Mod": 1})
    assert entity.hvac_mode == HVACMode.OFF


@pytest.mark.parametrize(
    ("device_mode", "expected"),
    [
        (0, HVACMode.AUTO),
        (1, HVACMode.COOL),
        (2, HVACMode.DRY),
        (3, HVACMode.FAN_ONLY),
        (4, HVACMode.HEAT),
    ],
)
def test_modes_map_correctly(device_mode: int, expected: HVACMode) -> None:
    entity, _ = _make_entity({"Pow": 1, "Mod": device_mode})
    assert entity.hvac_mode == expected


@pytest.mark.parametrize(
    ("speed", "expected"),
    [(0, FAN_AUTO), (1, FAN_LOW), (3, FAN_MEDIUM), (5, FAN_HIGH)],
)
def test_fan_modes_map_correctly(speed: int, expected: str) -> None:
    entity, _ = _make_entity({"Pow": 1, "Mod": 1, "WdSpd": speed})
    assert entity.fan_mode == expected


def test_target_and_current_temperature() -> None:
    entity, _ = _make_entity({"Pow": 1, "Mod": 1, "SetTem": 23, "TemSen": 25})
    assert entity.target_temperature == 23.0
    assert entity.current_temperature == 25.0


def test_implausible_temp_sensor_is_none() -> None:
    entity, _ = _make_entity({"Pow": 1, "Mod": 1, "TemSen": -50})
    assert entity.current_temperature is None


@pytest.mark.asyncio
async def test_set_temperature_emits_set_tem() -> None:
    entity, device = _make_entity({"Pow": 1, "Mod": 1, "SetTem": 22})
    await entity.async_set_temperature(temperature=24)
    device.set_state.assert_awaited_once_with({PARAM_SET_TEMP: 24})


@pytest.mark.asyncio
async def test_set_hvac_mode_off_emits_pow_zero() -> None:
    entity, device = _make_entity({"Pow": 1, "Mod": 1})
    await entity.async_set_hvac_mode(HVACMode.OFF)
    device.set_state.assert_awaited_once_with({PARAM_POWER: 0})


@pytest.mark.asyncio
async def test_set_hvac_mode_heat_emits_pow_on_and_mode_heat() -> None:
    entity, device = _make_entity({"Pow": 0})
    await entity.async_set_hvac_mode(HVACMode.HEAT)
    device.set_state.assert_awaited_once_with({PARAM_POWER: 1, PARAM_MODE: 4})


@pytest.mark.asyncio
async def test_set_fan_mode_high_emits_wdspd_5() -> None:
    entity, device = _make_entity({"Pow": 1, "Mod": 1})
    await entity.async_set_fan_mode(FAN_HIGH)
    device.set_state.assert_awaited_once_with({PARAM_FAN_SPEED: 5})


@pytest.mark.asyncio
async def test_turn_on_off_shortcuts() -> None:
    entity, device = _make_entity({"Pow": 0})
    await entity.async_turn_on()
    device.set_state.assert_awaited_with({PARAM_POWER: 1})
    await entity.async_turn_off()
    device.set_state.assert_awaited_with({PARAM_POWER: 0})


@pytest.mark.asyncio
async def test_failed_command_raises_home_assistant_error() -> None:
    entity, device = _make_entity({"Pow": 0})
    device.set_state.side_effect = EwpeTimeout("no reply")
    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on()
    entity.coordinator.async_request_refresh.assert_not_awaited()
