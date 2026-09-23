"""Tests for disabled-by-default entity policy."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.ewpe_smart.const import (
    PARAM_FAULT,
    PARAM_OUTDOOR_TEMP,
    PARAM_TEMP_SENSOR,
)
from custom_components.ewpe_smart.params_catalog import (
    ALL_KNOWN_PARAMS,
    CLIMATE_PARAMS,
    DISABLED_BY_DEFAULT_PARAMS,
    FAN_PARAMS,
    param_disabled_by_default,
)
from custom_components.ewpe_smart.sensor import (
    EwpeDiagnosticSensor,
    EwpeExtraSensor,
    EwpeIndoorTempSensor,
    supported_extra_sensor_descriptions,
)


def test_disabled_params_disjoint_from_climate_and_wind() -> None:
    assert not DISABLED_BY_DEFAULT_PARAMS & CLIMATE_PARAMS
    assert not DISABLED_BY_DEFAULT_PARAMS & FAN_PARAMS


def test_disabled_params_are_known_wire_keys() -> None:
    unknown = DISABLED_BY_DEFAULT_PARAMS - set(ALL_KNOWN_PARAMS)
    assert unknown == set()


def test_param_disabled_by_default_ignores_climate_keys() -> None:
    assert PARAM_TEMP_SENSOR in CLIMATE_PARAMS
    assert PARAM_TEMP_SENSOR not in DISABLED_BY_DEFAULT_PARAMS
    assert param_disabled_by_default(PARAM_TEMP_SENSOR) is False


def test_param_disabled_by_default_for_fault_and_outdoor() -> None:
    assert param_disabled_by_default(PARAM_FAULT) is True
    assert param_disabled_by_default(PARAM_OUTDOOR_TEMP) is False


def _make_extra_sensor(param: str, value: int) -> EwpeExtraSensor:
    status = {PARAM_OUTDOOR_TEMP: 22, param: value}
    description = next(
        d for d in supported_extra_sensor_descriptions(status) if d.param == param
    )
    coordinator = MagicMock()
    coordinator.data = status
    coordinator.last_update_success = True
    coordinator.async_add_listener = MagicMock(return_value=lambda: None)
    device = MagicMock()
    device.mac = "AA:BB:CC:DD:EE:FF"
    device.name = "Test"
    device.info = {}
    coordinator.device = device
    return EwpeExtraSensor(coordinator, description)


def test_extra_sensor_fault_disabled_by_default() -> None:
    entity = _make_extra_sensor(PARAM_FAULT, 0)
    assert entity.entity_registry_enabled_default is False


def test_extra_sensor_outdoor_temperature_not_disabled_by_default() -> None:
    entity = _make_extra_sensor(PARAM_OUTDOOR_TEMP, 22)
    assert entity.entity_registry_enabled_default is True


def test_indoor_temperature_not_disabled_by_default() -> None:
    coordinator = MagicMock()
    coordinator.data = {PARAM_TEMP_SENSOR: 22}
    device = MagicMock()
    device.mac = "AA:BB:CC:DD:EE:FF"
    device.name = "Test"
    device.info = {}
    coordinator.device = device
    entity = EwpeIndoorTempSensor(coordinator)
    assert entity.entity_registry_enabled_default is True


def test_diagnostic_fallback_always_disabled_by_default() -> None:
    coordinator = MagicMock()
    coordinator.data = {"NewTimer": 1}
    device = MagicMock()
    device.mac = "AA:BB:CC:DD:EE:FF"
    device.name = "Test"
    device.info = {}
    coordinator.device = device
    entity = EwpeDiagnosticSensor(coordinator, "NewTimer")
    assert entity.entity_registry_enabled_default is False
