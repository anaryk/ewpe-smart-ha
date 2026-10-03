# Integration architecture

## Purpose

Local-polling Home Assistant integration for air conditioners controlled via
the **EWPE Smart** mobile app (Daitsu, Gree, Cooper&Hunter, Sinclair, EcoAir,
ProKlima, and other brands sharing the same WiFi controller).

Unlike the [official HA Gree integration](https://www.home-assistant.io/integrations/gree/),
this one supports **manual IP entry** and targets units that fail broadcast
discovery (common with commercial cassette controllers). See
[references.md](references.md) for related projects and upstream PRs.

## Layer separation

Dependency direction is strictly top → bottom:

| Layer | Module | HA imports? | Responsibility |
|-------|--------|-------------|----------------|
| Protocol | `protocol.py` | No | AES encrypt/decrypt, UDP helpers, packet builders |
| Device | `device.py` | No | `EwpeDevice` — bind, status read, command write |
| Coordinator | `coordinator.py` | Yes | `DataUpdateCoordinator` polling loop |
| Config | `config_flow.py` | Yes | User flow, options flow, reauth flow |
| Entities | `entity.py`, `climate.py`, `sensor.py`, `select.py`, `switch.py`, `number.py`, `binary_sensor.py` | Yes | Map coordinator data to HA entities |
| Diagnostics | `diagnostics.py` | Yes | Redacted config entry and raw status for bug reports |

Layers 1–2 are Home Assistant–free and can be tested with plain pytest and
`tests/mock_device.py`.

## Lifecycle

### 1. Configuration

Two entry paths:

- **Manual IP** — user types the controller IP; integration runs scan+bind.
- **Network scan** — UDP broadcast discovers devices; user picks one from a
  list; bind runs on the selected IP.

`config_flow._bind_device()` creates an `EwpeDevice` and calls `bind()`.

### 2. Bind handshake

`EwpeDevice.bind()` → `protocol.scan_then_bind()`:

1. Send unencrypted `{"t":"scan"}` to the device IP on **UDP port 7000**.
2. Parse the `dev` reply — learn MAC (`cid`), name, model, protocol version.
3. On the **same UDP socket**, send encrypted `{"t":"bind","mac":…,"uid":0}`.
4. Receive `bindok` with a **device-specific 16-byte AES key** (stored in the
   config entry).

Many newer units advertise V1 on scan but only accept bind over **V2 (AES-GCM)**.
The integration tries both protocol versions on bind failure and persists the
working version in the config entry (`protocol_version`).

Bind must happen on the same socket immediately after scan — some firmware
rejects bind on a fresh socket (see [hardware-notes.md](hardware-notes.md)).

### 3. Polling

`EwpeCoordinator` calls `device.get_status()` every `update_interval` seconds
(default 30, configurable 10–300 in options).

Each poll sends:

```json
{"t": "status", "mac": "<mac>", "cols": ["Pow", "Mod", …]}
```

The device replies with matching `cols` and `dat` arrays. Only parameters the
firmware supports are returned — this drives entity discovery.

### 4. Entity setup

The coordinator is stored on `entry.runtime_data`. After the first refresh,
setup also reads model and firmware from a scan reply for the device info; a
failure there is logged and does not block setup.

Every entity derives from `EwpeEntity` (`entity.py`), which sets
`unique_id = f"{mac}_{key}"` and the shared device info. The `key` is the
catalog's `unique_id_suffix`, so renaming a suffix changes the entity_id in
existing installs.

On first coordinator refresh, each platform's `async_setup_entry` inspects
`coordinator.data`:

- **Always created:** climate, indoor temperature sensor.
- **Created if param in status:** swing selects, extra sensors, switches,
  numbers, binary sensors.

Entity lists are fixed after setup — params that appear later do not create new
entities (by design: no entity registry churn).

### 5. Commands

All writes go through `EwpeDevice.set_state(params)`:

```json
{"t": "cmd", "mac": "<mac>", "opt": ["SetTem"], "p": [24]}
```

The coordinator refreshes after each write so the UI updates promptly. A
failed write from climate or a catalog platform raises `HomeAssistantError`
(`command_failed`).

The unit beeps on every command it receives, so a call that changes several
params sends them in one packet. `climate.set_temperature` with `hvac_mode`
sends `Pow`, `Mod` and `SetTem` together.

### 6. Protocol version fallback

During normal operation, if a request fails with timeout or auth error on the
stored protocol version, the device layer retries on the alternate version and
updates the config entry when successful.

### 7. Re-authentication

If the stored device key can no longer decrypt replies (`EwpeAuthError`), the
coordinator raises `ConfigEntryAuthFailed` and HA prompts for reauth. Power-
cycle the unit if it was factory-reset, then submit to re-run bind.

## Config entry data

| Key | Meaning |
|-----|---------|
| `host` | Device IP address |
| `port` | UDP port (default 7000) |
| `mac` | Device MAC from scan |
| `key` | Device-specific encryption key (string) |
| `name` | Friendly name |
| `protocol_version` | `1` (AES-ECB) or `2` (AES-GCM) |

## Options

| Option | Default | Range |
|--------|---------|-------|
| `update_interval` | 30 | 10–300 seconds |

## Error handling

| Condition | Behaviour |
|-----------|-----------|
| UDP timeout or ICMP unreachable | Rediscover by MAC on the LAN, then `unavailable` via `UpdateFailed` |
| Bad decrypt with stored key | Reauth flow |
| Malformed reply | `unavailable` |
| Bind failure in config flow | "Could not reach the device on the supplied IP" |

## Platforms and entities

### Climate (`climate.py`)

Controls power, HVAC mode, target temperature and fan mode. Fan modes cover
auto and all five fixed steps; steps 2 and 4 are the custom modes `medium_low`
and `medium_high`.

| HA attribute | Wire param(s) |
|--------------|---------------|
| Power / HVAC mode | `Pow`, `Mod` |
| Target temperature | `SetTem` |
| Fan mode | `WdSpd` |
| Current temperature | `TemSen` (decoded) |

### Sensor (`sensor.py`)

| Entity | Wire param | Notes |
|--------|------------|-------|
| Indoor temperature | `TemSen` | Always present |
| Outdoor temperature | `OutEnvTem` | Hide-when-missing; decoded −40 |
| Fault code | `FaultDisplay` | Diagnostic category |

### Select (`select.py`)

| Entity | Wire param(s) | Notes |
|--------|---------------|-------|
| Horizontal swing | `SwingLfRig` | Hide-when-missing |
| Vertical swing | `SwUpDn` | Hide-when-missing |

### Switch (`switch.py`)

Binary 0/1 flags, one entity per wire key present in status `cols`. Eight
keys have hand-written descriptions (sleep, turbo, quiet, X-Fan, health,
display light, energy save, fresh air); sleep also writes `SlpMod`. Every
other switch key comes from the parameter catalog.

### Number (`number.py`)

Timers, sleep-curve steps, and other numeric setpoints. Hide-when-missing.

### Binary sensor (`binary_sensor.py`)

Maintenance alerts and status flags (`ReplaceHEPA`, `HasTmr`, …).

### Diagnostic fallback (`sensor.py`)

Any supported wire key without an explicit mapping becomes a read-only
diagnostic sensor showing the raw integer.

See [parameters.md](parameters.md) for the full entity list.

## Testing

- Unit tests use `tests/mock_device.py` (in-process UDP mock).
- `tests/test_entity_discovery.py` holds a decoded snapshot from a real unit
  and asserts which entities would be created.
- Hardware validation uses `tools/probe.py` — see [probe.md](probe.md).

## Related upstream work

| PR | Topic |
|----|-------|
| [#13](https://github.com/anaryk/ewpe-smart-ha/pull/13) | Hybrid V1/V2 bind handshake (`scan_then_bind` on one socket), merged |
| [#14](https://github.com/anaryk/ewpe-smart-ha/pull/14) | Switch entities, merged |
| [#43](https://github.com/anaryk/ewpe-smart-ha/pull/43) | Follow the device when its IP address changes, merged |
| [#15](https://github.com/anaryk/ewpe-smart-ha/pull/15) | Silent commands via `Buzzer_ON_OFF`, closed (the buzzer ignores it) |

This fork is upstream `main` plus the parameter catalog and the extra
platforms.

Full link list: [references.md](references.md).
