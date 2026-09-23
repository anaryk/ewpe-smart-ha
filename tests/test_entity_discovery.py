"""Tests for hide-when-missing entity discovery on a live unit snapshot."""

from __future__ import annotations

from custom_components.ewpe_smart.const import (
    PARAM_ANTI_DIRECT_BLOW,
    PARAM_BEEPER,
    PARAM_DRAIN_WATER_SENSOR,
    PARAM_FAN_SPEED,
    PARAM_FAULT,
    PARAM_HEAT_COOL_TYPE,
    PARAM_OUTDOOR_TEMP,
    PARAM_QUIET,
    PARAM_SENSOR_LIGHT,
    PARAM_SLEEP_MODE,
    PARAM_SMART_HEAT_8C,
    PARAM_SVST,
    PARAM_SWING_HORIZONTAL,
    PARAM_SWING_VERTICAL,
    PARAM_TEM_REC,
    PARAM_TUR,
)
from custom_components.ewpe_smart.params_catalog import diagnostic_params
from custom_components.ewpe_smart.select import supported_select_descriptions
from custom_components.ewpe_smart.sensor import supported_extra_sensor_descriptions
from custom_components.ewpe_smart.switch import supported_switch_descriptions

# Decoded status cols/values from hardware discovery.
UNIT_STATUS = {
    "Pow": 1,
    "Mod": 1,
    "SetTem": 22,
    "TemUn": 0,
    "WdSpd": 0,
    "TemSen": 21,
    "SwhSlp": 0,
    "Tur": 0,
    "Quiet": 0,
    "Blo": 0,
    "Health": 1,
    "Lig": 1,
    "SvSt": 0,
    "Air": 0,
    "SwingLfRig": 1,
    "SwUpDn": 6,
    "SlpMod": 0,
    "AntiDirectBlow": 0,
    "LigSen": 1,
    "OutEnvTem": 22,
    "DwatSen": 0,
    "FaultDisplay": 0,
    "StHt": 0,
    "Buzzer_ON_OFF": 1,
    "TemRec": 0,
    "HeatCoolType": 0,
}


def test_unit_snapshot_entity_surface() -> None:
    switches = {d.param for d in supported_switch_descriptions(UNIT_STATUS)}
    selects = {d.param for d in supported_select_descriptions(UNIT_STATUS)}
    sensors = {d.param for d in supported_extra_sensor_descriptions(UNIT_STATUS)}

    assert PARAM_FAN_SPEED in UNIT_STATUS
    assert PARAM_QUIET in UNIT_STATUS
    assert PARAM_TUR in UNIT_STATUS
    assert selects == {PARAM_SWING_HORIZONTAL, PARAM_SWING_VERTICAL}
    assert sensors == {
        PARAM_OUTDOOR_TEMP,
        PARAM_DRAIN_WATER_SENSOR,
        PARAM_FAULT,
        PARAM_HEAT_COOL_TYPE,
    }
    assert {
        PARAM_SLEEP_MODE,
        "SwhSlp",
        PARAM_ANTI_DIRECT_BLOW,
        PARAM_SENSOR_LIGHT,
        PARAM_SMART_HEAT_8C,
        PARAM_BEEPER,
        PARAM_SVST,
    }.issubset(switches)


def test_internal_params_use_explicit_entities_not_fallback() -> None:
    data = {**UNIT_STATUS, "NewTimer": 1}
    raw = diagnostic_params(data)
    assert "NewTimer" not in raw
    assert PARAM_TEM_REC not in raw
    assert "Pow" not in raw
    assert "SwhSlp" not in raw
