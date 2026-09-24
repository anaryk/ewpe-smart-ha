"""Constants for the EWPE Smart integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "ewpe_smart"
MANUFACTURER = "Gree (EWPE Smart)"

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.BINARY_SENSOR,
]

# Network
DEFAULT_PORT = 7000
DEFAULT_TIMEOUT = 5.0
DEFAULT_BIND_TIMEOUT = 10.0
DEFAULT_BROADCAST = "255.255.255.255"
DEFAULT_SCAN_TIMEOUT = 3.0

# Encryption — V1 (AES-ECB, original Gree firmware)
GENERIC_KEY = b"a3K8Bx%2r8Y7#xDh"

# Encryption — V2 (AES-GCM, newer Gree firmware on commercial U-Match,
# XE7A-style controllers, and recent split units). Devices opt into V2
# by including a `tag` field next to `pack` in the envelope.
GENERIC_KEY_V2 = b"{yxAHAY_Lm6pbC/<"
GCM_NONCE = b"\x54\x40\x78\x44\x49\x67\x5a\x51\x6c\x5e\x63\x13"
GCM_AAD = b"qualcomm-test"

PROTO_V1 = 1
PROTO_V2 = 2

# Polling
DEFAULT_UPDATE_INTERVAL = 30
MIN_UPDATE_INTERVAL = 10
MAX_UPDATE_INTERVAL = 300

# Temperature sensor offset applied to raw wire values (TemSen, OutEnvTem, …)
TEMP_SENSOR_OFFSET = -40

# Config entry keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_MAC = "mac"
CONF_KEY = "key"
CONF_NAME = "name"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_BROADCAST = "broadcast"
CONF_VERSION = "protocol_version"

# ── Device parameter keys ──────────────────────────────────────────────────
PARAM_POWER = "Pow"
PARAM_MODE = "Mod"
PARAM_SET_TEMP = "SetTem"
PARAM_TEMP_UNIT = "TemUn"
PARAM_FAN_SPEED = "WdSpd"
PARAM_TEMP_SENSOR = "TemSen"

PARAM_SLEEP = "SwhSlp"
# Firmware keeps the sleep curve in SlpMod; SwhSlp alone is a no-op on some
# units, so both are written together (greeclimate does the same).
PARAM_SLEEP_MODE = "SlpMod"
PARAM_TUR = "Tur"
PARAM_QUIET = "Quiet"
PARAM_BLO = "Blo"
PARAM_HEALTH = "Health"
PARAM_LIG = "Lig"
PARAM_SVST = "SvSt"
PARAM_AIR = "Air"

PARAM_SWING_HORIZONTAL = "SwingLfRig"
PARAM_SWING_VERTICAL = "SwUpDn"
PARAM_SUB_ZONE_SWING_UD = "DnPUDSwing"
PARAM_SUB_ZONE_SWING_RIGHT = "DnPRLRSwing"
PARAM_SUB_ZONE_SWING_LEFT = "DnPLLRSwing"
PARAM_ANTI_DIRECT_BLOW = "AntiDirectBlow"
PARAM_SENSOR_LIGHT = "LigSen"
PARAM_OUTDOOR_TEMP = "OutEnvTem"
PARAM_DRAIN_WATER_SENSOR = "DwatSen"
PARAM_HUMIDITY = "Wet"
PARAM_FAULT = "FaultDisplay"
PARAM_TEM_REC = "TemRec"
PARAM_HEAT_COOL_TYPE = "HeatCoolType"
PARAM_SMART_HEAT_8C = "StHt"
PARAM_BEEPER = "Buzzer_ON_OFF"

SWITCH_PARAMS: list[str] = [
    PARAM_SLEEP,
    PARAM_TUR,
    PARAM_QUIET,
    PARAM_BLO,
    PARAM_HEALTH,
    PARAM_LIG,
    PARAM_SVST,
    PARAM_AIR,
]

STATUS_PARAMS: list[str] = [
    PARAM_POWER,
    PARAM_MODE,
    PARAM_SET_TEMP,
    PARAM_TEMP_UNIT,
    PARAM_FAN_SPEED,
    PARAM_TEMP_SENSOR,
    *SWITCH_PARAMS,
]

# ── Value mappings ─────────────────────────────────────────────────────────
POWER_OFF = 0
POWER_ON = 1

# The EWPE Smart and Gree apps switch quiet on with 2; some firmware drops a
# plain 1 after a while (greeclimate issue 87). Any non-zero value reads as on.
QUIET_MODE_ON = 2

MODE_AUTO = 0
MODE_COOL = 1
MODE_DRY = 2
MODE_FAN = 3
MODE_HEAT = 4

FAN_SPEED_AUTO = 0
FAN_SPEED_LOW = 1
FAN_SPEED_MEDIUM_LOW = 2
FAN_SPEED_MEDIUM = 3
FAN_SPEED_MEDIUM_HIGH = 4
FAN_SPEED_HIGH = 5

# Temperature limits
MIN_TEMP = 16
MAX_TEMP = 30

# Horizontal fixed positions match the native app (direction1–5 → wire values 2–6).
SWING_HORIZONTAL_DEVICE_TO_OPTION: dict[int, str] = {
    1: "full_swing",
    2: "left",
    3: "left_center",
    4: "center",
    5: "right_center",
    6: "right",
}

# Vertical fixed positions match the native app (direction1–5 → wire values 2–6).
# Partial-swing variants (7–11) are experimental — see docs/parameters.md.
SWING_VERTICAL_DEVICE_TO_OPTION: dict[int, str] = {
    1: "full_swing",
    2: "fixed_upper",
    3: "fixed_upper_middle",
    4: "fixed_middle",
    5: "fixed_lower_middle",
    6: "fixed_lower",
    7: "swing_upper",
    8: "swing_upper_middle",
    9: "swing_middle",
    10: "swing_lower_middle",
    11: "swing_lower",
}
