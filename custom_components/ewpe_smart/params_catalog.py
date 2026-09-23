"""Wire parameter catalog, alias groups, and entity discovery helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

# Device payload reference count (distinct cols from a full EWPE Smart extraction).
EXPECTED_DEVICE_PARAM_COUNT = 140

_WIRE_PARAMS_PATH = Path(__file__).resolve().parent / "data" / "wire_params.json"


def _load_known_params() -> tuple[str, ...]:
    """Load the wire-key catalog used for first-poll discovery."""
    with _WIRE_PARAMS_PATH.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    params = payload["params"]
    if not isinstance(params, list) or not params:
        raise ValueError(f"{_WIRE_PARAMS_PATH} must contain a non-empty params list")
    if len(params) != len(set(params)):
        msg = "duplicate wire parameter names in wire_params.json"
        raise ValueError(msg)
    return tuple(params)


# Full catalog (requested on first status poll). Devices echo only the subset
# they support in status ``cols``. See custom_components/ewpe_smart/data/wire_params.json — must match the
# device payload (140 distinct keys on reference hardware).
ALL_KNOWN_PARAMS: tuple[str, ...] = _load_known_params()

# Some firmware (e.g. V3.4.M on V2 crypto) stops replying when ``cols`` exceeds ~57.
DISCOVERY_BATCH_SIZE = 50


def param_batches(
    params: Sequence[str],
    batch_size: int = DISCOVERY_BATCH_SIZE,
) -> tuple[tuple[str, ...], ...]:
    """Split a column list into firmware-safe status request batches."""
    items = list(params)
    if not items:
        return ()
    return tuple(
        tuple(items[index : index + batch_size])
        for index in range(0, len(items), batch_size)
    )


# Params decoded with TEMP_SENSOR_OFFSET (−40) in device.get_status().
TEMP_OFFSET_PARAMS: frozenset[str] = frozenset(
    {
        "TemSen",
        "OutEnvTem",
        "EnvTem",
        "TemsSenOut",
        "InEvaTem",
        "CpsTem",
        "CompressorTem",
    }
)

# Owned by the climate entity — never generic diagnostic.
CLIMATE_PARAMS: frozenset[str] = frozenset({"Pow", "Mod", "SetTem", "TemUn", "TemSen"})

# Owned by climate fan_mode and the quiet/turbo switches — never generic diagnostic.
FAN_PARAMS: frozenset[str] = frozenset({"WdSpd", "Quiet", "Tur"})

# Wire keys switch.py describes by hand; the catalog adds switches for the rest.
CORE_SWITCH_PARAMS: frozenset[str] = frozenset(
    {"SwhSlp", "Tur", "Quiet", "Blo", "Health", "Lig", "SvSt", "Air"}
)


def _slug_from_param(param: str) -> str:
    """Build a stable unique_id / translation suffix from a wire key."""
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", param).strip("_").lower()
    return slug or "param"


@dataclass(frozen=True, kw_only=True)
class SwitchDescriptionRef:
    """One switch entity per wire key (hide-when-missing)."""

    param: str
    unique_id_suffix: str
    translation_key: str


def _switch(
    param: str,
    *,
    unique_id_suffix: str | None = None,
    translation_key: str | None = None,
) -> SwitchDescriptionRef:
    slug = unique_id_suffix or _slug_from_param(param)
    return SwitchDescriptionRef(
        param=param,
        unique_id_suffix=slug,
        translation_key=translation_key or slug,
    )


# One HA switch per wire key — no priority collapse when firmware echoes several.
SWITCH_DESCRIPTIONS: tuple[SwitchDescriptionRef, ...] = (
    _switch(
        "SmartSlpMod",
        translation_key="smart_slp_mod",
        unique_id_suffix="smart_slp_mod",
    ),
    _switch("SlpMod", translation_key="slp_mod", unique_id_suffix="slp_mod"),
    _switch("Emod"),
    _switch(
        "Dazzling",
        translation_key="anti_dazzle",
        unique_id_suffix="anti_dazzle",
    ),
    _switch("LedLight", translation_key="led_light", unique_id_suffix="led_light"),
    _switch(
        "LedLig", translation_key="led_light_zone", unique_id_suffix="led_light_zone"
    ),
    _switch(
        "DsplySt",
        translation_key="display_state_switch",
        unique_id_suffix="display_state_switch",
    ),
    _switch(
        "NobodySave",
        translation_key="nobody_save",
        unique_id_suffix="nobody_save",
    ),
    _switch(
        "BuzzerCtrl",
        translation_key="buzzer_ctrl",
        unique_id_suffix="buzzer_ctrl",
    ),
    _switch(
        "Buzzer_ON_OFF",
        translation_key="buzzer_on_off",
        unique_id_suffix="buzzer_on_off",
    ),
    _switch(
        "AntiDirectBlow",
        translation_key="anti_direct_blow",
        unique_id_suffix="anti_direct_blow",
    ),
    _switch(
        "LigSen",
        translation_key="light_sensor",
        unique_id_suffix="light_sensor",
    ),
    _switch("StHt", translation_key="smart_heat_8c", unique_id_suffix="smart_heat_8c"),
    _switch("ChildLock", translation_key="child_lock", unique_id_suffix="child_lock"),
    _switch("AutoClean", translation_key="auto_clean", unique_id_suffix="auto_clean"),
    _switch(
        "UvcControl", translation_key="uvc_control", unique_id_suffix="uvc_control"
    ),
    _switch("CoolFeel", translation_key="cool_feel", unique_id_suffix="cool_feel"),
    _switch("SmartWind", translation_key="smart_wind", unique_id_suffix="smart_wind"),
    _switch(
        "AutoPowReduce",
        translation_key="auto_pow_reduce",
        unique_id_suffix="auto_pow_reduce",
    ),
    _switch(
        "UnmanedShutDown",
        translation_key="unoccupied_shutdown",
        unique_id_suffix="unoccupied_shutdown",
    ),
    _switch("TmrOn", translation_key="timer_start", unique_id_suffix="timer_start"),
    _switch("TmrOff", translation_key="timer_stop", unique_id_suffix="timer_stop"),
)

SWITCH_PARAM_NAMES: frozenset[str] = frozenset(
    desc.param for desc in SWITCH_DESCRIPTIONS
)


def _sensor_ref(
    param: str,
    *,
    unique_id_suffix: str | None = None,
    translation_key: str | None = None,
    value_kind: Literal["int", "text"] = "int",
    entity_category: str | None = "diagnostic",
    **kwargs: Any,
) -> SensorDescriptionRef:
    slug = unique_id_suffix or _slug_from_param(param)
    return SensorDescriptionRef(
        param=param,
        unique_id_suffix=slug,
        translation_key=translation_key or slug,
        value_kind=value_kind,
        entity_category=entity_category,
        **kwargs,
    )


@dataclass(frozen=True, kw_only=True)
class SensorDescriptionRef:
    """Lightweight sensor spec used by sensor.py."""

    param: str
    unique_id_suffix: str
    translation_key: str
    device_class: str | None = None
    state_class: str | None = None
    entity_category: str | None = None
    native_unit_of_measurement: str | None = None
    percent_range: bool = False
    value_kind: Literal["int", "text"] = "int"


EXTRA_SENSOR_DESCRIPTIONS: tuple[SensorDescriptionRef, ...] = (
    SensorDescriptionRef(
        param="OutEnvTem",
        unique_id_suffix="outdoor_temperature",
        translation_key="outdoor_temperature",
        device_class="temperature",
        state_class="measurement",
        native_unit_of_measurement="°C",
    ),
    SensorDescriptionRef(
        param="DwatSen",
        unique_id_suffix="drain_water_sensor",
        translation_key="drain_water_sensor",
        entity_category="diagnostic",
    ),
    SensorDescriptionRef(
        param="Wet",
        unique_id_suffix="humidity",
        translation_key="humidity",
        device_class="humidity",
        state_class="measurement",
        native_unit_of_measurement="%",
        percent_range=True,
    ),
    SensorDescriptionRef(
        param="FaultDisplay",
        unique_id_suffix="fault",
        translation_key="fault",
        entity_category="diagnostic",
    ),
    SensorDescriptionRef(
        param="PM2P5",
        unique_id_suffix="pm25",
        translation_key="pm25",
        device_class="pm25",
        state_class="measurement",
        native_unit_of_measurement="µg/m³",
    ),
    SensorDescriptionRef(
        param="Dfltr",
        unique_id_suffix="filter_status",
        translation_key="filter_status",
        entity_category="diagnostic",
    ),
    SensorDescriptionRef(
        param="AllErr",
        unique_id_suffix="all_errors",
        translation_key="all_errors",
        entity_category="diagnostic",
    ),
    SensorDescriptionRef(
        param="JFErrorCode",
        unique_id_suffix="jf_error_code",
        translation_key="jf_error_code",
        entity_category="diagnostic",
    ),
    SensorDescriptionRef(
        param="SubhealthFault",
        unique_id_suffix="subhealth_fault",
        translation_key="subhealth_fault",
        entity_category="diagnostic",
    ),
    SensorDescriptionRef(
        param="ShutdownFault",
        unique_id_suffix="shutdown_fault",
        translation_key="shutdown_fault",
        entity_category="diagnostic",
    ),
    SensorDescriptionRef(
        param="FbidBloPer",
        unique_id_suffix="forbidden_blow_period",
        translation_key="forbidden_blow_period",
        entity_category="diagnostic",
        native_unit_of_measurement="%",
        percent_range=True,
    ),
    SensorDescriptionRef(
        param="EnvTem",
        unique_id_suffix="environment_temperature",
        translation_key="environment_temperature",
        device_class="temperature",
        state_class="measurement",
        native_unit_of_measurement="°C",
    ),
    SensorDescriptionRef(
        param="InEvaTem",
        unique_id_suffix="indoor_evaporator_temperature",
        translation_key="indoor_evaporator_temperature",
        device_class="temperature",
        state_class="measurement",
        native_unit_of_measurement="°C",
        entity_category="diagnostic",
    ),
    SensorDescriptionRef(
        param="CpsTem",
        unique_id_suffix="compressor_temperature",
        translation_key="compressor_temperature",
        device_class="temperature",
        state_class="measurement",
        native_unit_of_measurement="°C",
        entity_category="diagnostic",
    ),
    SensorDescriptionRef(
        param="CompressorTem",
        unique_id_suffix="compressor_temperature_alt",
        translation_key="compressor_temperature_alt",
        device_class="temperature",
        state_class="measurement",
        native_unit_of_measurement="°C",
        entity_category="diagnostic",
    ),
    SensorDescriptionRef(
        param="CompressorFqy",
        unique_id_suffix="compressor_frequency",
        translation_key="compressor_frequency",
        state_class="measurement",
        native_unit_of_measurement="Hz",
        entity_category="diagnostic",
    ),
    SensorDescriptionRef(
        param="TemsSenOut",
        unique_id_suffix="outdoor_sensor_temperature",
        translation_key="outdoor_sensor_temperature",
        device_class="temperature",
        state_class="measurement",
        native_unit_of_measurement="°C",
        entity_category="diagnostic",
    ),
    SensorDescriptionRef(
        param="AutoCleanSta",
        unique_id_suffix="auto_clean_status",
        translation_key="auto_clean_status",
        entity_category="diagnostic",
    ),
    SensorDescriptionRef(
        param="AutoCleanStaEx",
        unique_id_suffix="auto_clean_status_extended",
        translation_key="auto_clean_status_extended",
        entity_category="diagnostic",
    ),
    SensorDescriptionRef(
        param="HeatCoolType",
        unique_id_suffix="heat_cool_type",
        translation_key="heat_cool_type",
        entity_category="diagnostic",
    ),
    SensorDescriptionRef(
        param="PowReduceType",
        unique_id_suffix="power_reduce_type",
        translation_key="power_reduce_type",
        entity_category="diagnostic",
    ),
    SensorDescriptionRef(
        param="PowReduceGear",
        unique_id_suffix="power_reduce_gear",
        translation_key="power_reduce_gear",
        entity_category="diagnostic",
    ),
)

# Wire keys without another platform mapping — explicit diagnostic / text sensors.
_REMAINING_SENSOR_PARAMS: tuple[tuple[str, Literal["int", "text"]], ...] = (
    ("Add0.1", "text"),
    ("Add0.5", "text"),
    ("AppTimer", "int"),
    ("AssHt", "int"),
    ("BlkTemCom", "int"),
    ("Coolmod", "int"),
    ("DFPoint", "int"),
    ("Dmod", "int"),
    ("DwatFul", "int"),
    ("Dwet", "int"),
    ("ElcAllKwhClr", "int"),
    ("ElcEn", "int"),
    ("EnvFun", "int"),
    ("HeatCool", "int"),
    ("ImgUpdateCol", "text"),
    ("ImgVerSta", "int"),
    ("ModelNew", "int"),
    ("ModelType", "text"),
    ("NewTimer", "int"),
    ("UniqueCode", "text"),
    ("VocCtl", "int"),
    ("VocIdiom", "int"),
    ("VocRole", "int"),
    ("VocUpdateCol", "text"),
    ("VocVerSta", "int"),
    ("Wind", "int"),
    ("bc", "text"),
    ("busVol", "int"),
    ("header", "text"),
    ("hid", "text"),
    ("host", "text"),
    ("mac", "text"),
    ("mid", "text"),
    ("name", "text"),
    ("vender", "text"),
    ("ver", "text"),
    ("wifiReset", "int"),
    ("wifiStatus", "int"),
    *tuple((f"EnvArea{i}St", "int") for i in range(1, 10)),
    *tuple((f"estateInsta{i}", "int") for i in range(21, 25)),
)

REMAINING_SENSOR_DESCRIPTIONS: tuple[SensorDescriptionRef, ...] = tuple(
    _sensor_ref(param, value_kind=kind) for param, kind in _REMAINING_SENSOR_PARAMS
)

EXTRA_SENSOR_DESCRIPTIONS: tuple[SensorDescriptionRef, ...] = (
    *EXTRA_SENSOR_DESCRIPTIONS,
    *REMAINING_SENSOR_DESCRIPTIONS,
)

EXPLICIT_SENSOR_PARAMS: frozenset[str] = frozenset(
    desc.param for desc in EXTRA_SENSOR_DESCRIPTIONS
)


@dataclass(frozen=True, kw_only=True)
class BinarySensorDescriptionRef:
    param: str
    unique_id_suffix: str
    translation_key: str
    device_class: str | None = None


BINARY_SENSOR_DESCRIPTIONS: tuple[BinarySensorDescriptionRef, ...] = (
    BinarySensorDescriptionRef(
        param="ReplaceHEPA",
        unique_id_suffix="replace_hepa",
        translation_key="replace_hepa",
        device_class="problem",
    ),
    BinarySensorDescriptionRef(
        param="HasTmr",
        unique_id_suffix="has_timer",
        translation_key="has_timer",
    ),
    BinarySensorDescriptionRef(
        param="MicroSen",
        unique_id_suffix="motion",
        translation_key="motion",
        device_class="motion",
    ),
    BinarySensorDescriptionRef(
        param="Dpump",
        unique_id_suffix="drain_pump",
        translation_key="drain_pump",
        device_class="running",
    ),
)

EXPLICIT_BINARY_SENSOR_PARAMS: frozenset[str] = frozenset(
    desc.param for desc in BINARY_SENSOR_DESCRIPTIONS
)


@dataclass(frozen=True, kw_only=True)
class NumberDescriptionRef:
    param: str
    unique_id_suffix: str
    translation_key: str
    native_min_value: float
    native_max_value: float
    native_step: float = 1.0
    native_unit_of_measurement: str | None = None
    mode: str = "auto"


NUMBER_DESCRIPTIONS: tuple[NumberDescriptionRef, ...] = (
    NumberDescriptionRef(
        param="TmrOnMinLf",
        unique_id_suffix="timer_on_minutes_left",
        translation_key="timer_on_minutes_left",
        native_min_value=0,
        native_max_value=1440,
        native_unit_of_measurement="min",
    ),
    NumberDescriptionRef(
        param="TmrOffMinLf",
        unique_id_suffix="timer_off_minutes_left",
        translation_key="timer_off_minutes_left",
        native_min_value=0,
        native_max_value=1440,
        native_unit_of_measurement="min",
    ),
    NumberDescriptionRef(
        param="TmrLpTms",
        unique_id_suffix="timer_loop_times",
        translation_key="timer_loop_times",
        native_min_value=0,
        native_max_value=255,
    ),
    NumberDescriptionRef(
        param="UnmanedOffTime",
        unique_id_suffix="unoccupied_off_time",
        translation_key="unoccupied_off_time",
        native_min_value=0,
        native_max_value=1440,
        native_unit_of_measurement="min",
    ),
    NumberDescriptionRef(
        param="TemRec",
        unique_id_suffix="temperature_display_offset",
        translation_key="temperature_display_offset",
        native_min_value=0,
        native_max_value=10,
        native_step=0.5,
        native_unit_of_measurement="°C",
    ),
    NumberDescriptionRef(
        param="UDFanPort",
        unique_id_suffix="up_down_fan_port",
        translation_key="up_down_fan_port",
        native_min_value=0,
        native_max_value=11,
    ),
    *(
        NumberDescriptionRef(
            param=f"Slp1L{i}",
            unique_id_suffix=f"sleep_curve_low_{i}",
            translation_key=f"sleep_curve_low_{i}",
            native_min_value=16,
            native_max_value=30,
            native_unit_of_measurement="°C",
        )
        for i in range(1, 9)
    ),
    *(
        NumberDescriptionRef(
            param=f"Slp1H{i}",
            unique_id_suffix=f"sleep_curve_high_{i}",
            translation_key=f"sleep_curve_high_{i}",
            native_min_value=16,
            native_max_value=30,
            native_unit_of_measurement="°C",
        )
        for i in range(1, 9)
    ),
)

EXPLICIT_NUMBER_PARAMS: frozenset[str] = frozenset(
    desc.param for desc in NUMBER_DESCRIPTIONS
)

SELECT_PARAM_NAMES: frozenset[str] = frozenset(
    {
        "SwingLfRig",
        "SwUpDn",
        "DnPUDSwing",
        "DnPRLRSwing",
        "DnPLLRSwing",
    }
)


def _explicit_entity_params() -> frozenset[str]:
    return frozenset(
        CLIMATE_PARAMS
        | FAN_PARAMS
        | CORE_SWITCH_PARAMS
        | SWITCH_PARAM_NAMES
        | EXPLICIT_SENSOR_PARAMS
        | EXPLICIT_BINARY_SENSOR_PARAMS
        | EXPLICIT_NUMBER_PARAMS
        | SELECT_PARAM_NAMES
        | {"TemSen"}  # indoor temp sensor (separate from climate attr)
    )


EXPLICIT_ENTITY_PARAMS: frozenset[str] = _explicit_entity_params()

# ── Disabled by default (HA entity registry) ───────────────────────────────
# Optional hardware, model-specific, internal diagnostics, destructive cols,
# and low-value system state. Users enable entities in HA when hardware matches.
# See docs/parameters.md — canonical list; do not disable CLIMATE_PARAMS here.

DISABLED_BY_DEFAULT_OPTIONAL_HARDWARE: frozenset[str] = frozenset(
    {
        "MicroSen",
        "UnmanedShutDown",
        "UnmanedOffTime",
        "NobodySave",
    }
)

DISABLED_BY_DEFAULT_MODEL_SPECIFIC: frozenset[str] = frozenset(
    {
        "AssHt",
        "AutoClean",
        "AutoCleanSta",
        "AutoCleanStaEx",
        "DnPLLRSwing",
        "DnPRLRSwing",
        "DnPUDSwing",
        "LigSen",
        "PM2P5",
        "ReplaceHEPA",
        "UDFanPort",
        "UvcControl",
        *(f"EnvArea{i}St" for i in range(1, 10)),
    }
)

DISABLED_BY_DEFAULT_DIAGNOSTIC: frozenset[str] = frozenset(
    {
        "AllErr",
        "BlkTemCom",
        "CompressorFqy",
        "CompressorTem",
        "CpsTem",
        "DFPoint",
        "Dpump",
        "DwatFul",
        "DwatSen",
        "FaultDisplay",
        "FbidBloPer",
        "HeatCoolType",
        "InEvaTem",
        "JFErrorCode",
        "PowReduceGear",
        "PowReduceType",
        "ShutdownFault",
        "SubhealthFault",
        "TemsSenOut",
        "busVol",
        *(f"Slp1H{i}" for i in range(1, 9)),
        *(f"Slp1L{i}" for i in range(1, 9)),
    }
)

DISABLED_BY_DEFAULT_DESTRUCTIVE: frozenset[str] = frozenset(
    {
        "ElcAllKwhClr",
        "wifiReset",
        *(f"estateInsta{i}" for i in range(21, 25)),
    }
)

DISABLED_BY_DEFAULT_NOISY: frozenset[str] = frozenset(
    {
        "ElcEn",
        "ImgUpdateCol",
        "ImgVerSta",
        "VocUpdateCol",
        "VocVerSta",
        "wifiStatus",
    }
)

DISABLED_BY_DEFAULT_PARAMS: frozenset[str] = (
    DISABLED_BY_DEFAULT_OPTIONAL_HARDWARE
    | DISABLED_BY_DEFAULT_MODEL_SPECIFIC
    | DISABLED_BY_DEFAULT_DIAGNOSTIC
    | DISABLED_BY_DEFAULT_DESTRUCTIVE
    | DISABLED_BY_DEFAULT_NOISY
)


def param_disabled_by_default(param: str) -> bool:
    """Whether Home Assistant should register the entity disabled by default."""
    if param in CLIMATE_PARAMS or param in FAN_PARAMS or param in CORE_SWITCH_PARAMS:
        return False
    return param in DISABLED_BY_DEFAULT_PARAMS


def diagnostic_params(data: Mapping[str, Any]) -> tuple[str, ...]:
    """Return unmapped wire keys that should become generic diagnostic sensors."""
    return tuple(sorted(param for param in data if param not in EXPLICIT_ENTITY_PARAMS))


def poll_params(supported: Sequence[str] | None) -> list[str]:
    """Return the column list for a runtime status poll."""
    if supported:
        return list(supported)
    return list(ALL_KNOWN_PARAMS)
