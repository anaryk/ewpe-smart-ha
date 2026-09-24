"""Tests for extra sensor entity discovery and values."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.ewpe_smart.const import (
    PARAM_DRAIN_WATER_SENSOR,
    PARAM_FAULT,
    PARAM_HUMIDITY,
    PARAM_OUTDOOR_TEMP,
)
from custom_components.ewpe_smart.sensor import (
    EwpeExtraSensor,
    supported_extra_sensor_descriptions,
)


def _make_sensor(param: str, value: int) -> EwpeExtraSensor:
    status = {PARAM_OUTDOOR_TEMP: 22, PARAM_FAULT: 0, param: value}
    descriptions = supported_extra_sensor_descriptions(status)
    description = next(d for d in descriptions if d.param == param)

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


def test_supported_extra_sensor_descriptions_excludes_placeholder_mac() -> None:
    data = {PARAM_OUTDOOR_TEMP: 22, "mac": 0}
    descriptions = supported_extra_sensor_descriptions(data)
    params = {d.param for d in descriptions}
    assert params == {PARAM_OUTDOOR_TEMP}


def test_supported_extra_sensor_descriptions_includes_valid_mac() -> None:
    data = {PARAM_OUTDOOR_TEMP: 22, "mac": "580d0df2deaf"}
    descriptions = supported_extra_sensor_descriptions(data)
    params = {d.param for d in descriptions}
    assert params == {PARAM_OUTDOOR_TEMP, "mac"}


def test_supported_extra_sensor_descriptions_filters_by_status_keys() -> None:
    data = {
        "Pow": 1,
        PARAM_OUTDOOR_TEMP: 22,
        PARAM_DRAIN_WATER_SENSOR: 1,
        PARAM_HUMIDITY: 45,
        PARAM_FAULT: 0,
    }
    descriptions = supported_extra_sensor_descriptions(data)
    params = {d.param for d in descriptions}
    assert params == {
        PARAM_OUTDOOR_TEMP,
        PARAM_DRAIN_WATER_SENSOR,
        PARAM_HUMIDITY,
        PARAM_FAULT,
    }


def test_outdoor_temperature_reads_decoded_value() -> None:
    entity = _make_sensor(PARAM_OUTDOOR_TEMP, 22)
    assert entity.native_value == 22.0


def test_fault_reads_numeric_code() -> None:
    entity = _make_sensor(PARAM_FAULT, 0)
    assert entity.native_value == 0


def test_drain_water_sensor_reads_raw_value() -> None:
    entity = _make_sensor(PARAM_DRAIN_WATER_SENSOR, 1)
    assert entity.native_value == 1


def test_humidity_reads_percent_value() -> None:
    entity = _make_sensor(PARAM_HUMIDITY, 45)
    assert entity.native_value == 45.0


def test_humidity_reads_zero_as_valid_value() -> None:
    entity = _make_sensor(PARAM_HUMIDITY, 0)
    assert entity.native_value == 0.0
