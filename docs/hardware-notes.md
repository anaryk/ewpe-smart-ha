# Hardware testing notes

Findings from live testing on a **Daitsu** unit controlled via the EWPE Smart
app. Other brands may differ — treat these as data points, not universal rules.

Source: probe snapshots and HA smoke tests documented in project chat sessions
(2026). Cross-check wire keys against
[gree-remote](https://github.com/tomikaa87/gree-remote/blob/master/README.md)
and [gree_custom `api.py`](https://github.com/p-monteiro/HomeAssistant-GreeClimateComponent-Rewrite/blob/e5ed1952102c104f0232ca816c87ed8bbd46c9d7/custom_components/gree_custom/aiogree/api.py);
see [references.md](references.md).

## Unit snapshot (reference)

A tested unit returned 26 of 27 requested discovery columns. Decoded highlights:

| Param | Raw wire | Decoded / meaning |
|-------|----------|-------------------|
| `TemSen` | 61 | 21 °C (offset −40) |
| `OutEnvTem` | 62 | 22 °C (offset −40) |
| `SwingLfRig` | 1 | Full swing |
| `SwUpDn` | 6 | Fixed lower |
| `WdSpd` | 0 | Auto |
| `DwatSen` | 0 | Drain water sensor — always 0 on tested unit |
| `Wet` | — | Humidity key — not echoed on tested unit |
| `StHt` | 0 | 8 °C heat — present but ineffective |
| `Buzzer_ON_OFF` | 1 | Beeper on — switch entity did not change behaviour |

`BuzzerCtrl` was absent from the reply.

## Confirmed working

- Outdoor temperature sensor (`OutEnvTem`) with −40 offset
- Horizontal swing fixed positions (left, center, right, full swing)
- Vertical swing fixed positions (upper → lower, full swing)
- All five fixed fan steps (`WdSpd` 1–5) plus auto
- Standard switches: sleep, X-fan, health, display light, energy save, fresh air,
  sleep mode, anti direct blow, auto display, 8 °C heat (`StHt`)

## Known limitations on tested hardware

These entities are exposed when the device returns the param in status `cols`,
but behaviour on the reference Daitsu unit was unreliable:

### 8 °C heating (`StHt`) — `switch.smart_heat_8c`

Parameter appears in status and the switch reflects the wire value, but toggling
had **no visible effect** in the native app or HA on tested hardware. The entity
is still useful for monitoring and for units where the feature works.

### Drain water (`DwatSen`) — `sensor.drain_water_sensor`

Parameter appears in status but value stayed **0** on tested hardware. Mapped as
a drain-water diagnostic per Gree parameter reference (not humidity).

### Humidity (`Wet`) — `sensor.humidity`

Use `Wet` for relative humidity when the device echoes it. The reference unit did
not return `Wet` in `cols`; do not use `DwatSen` for humidity.

### Beeper switch (`Buzzer_ON_OFF`)

Entity was implemented but **did not control the panel beep** on tested hardware.
A separate design explored appending `Buzzer_ON_OFF=1` to every HA **command**
(silent commands option) — that suppresses beeps on some firmware but is distinct
from a persistent beeper toggle.

### Vertical swing values 7–11 — experimental

Partial-swing wire values are available in `select.swing_vertical` but caused
**full-swing misbehaviour** when selected on this unit. Prefer fixed positions
(2–6) unless verified on your firmware. See [parameters.md](parameters.md).

## Fan: step, quiet and turbo

The EWPE Smart app shows one control (Auto, Low → High, Quiet, Turbo). The
integration keeps the three wire keys apart: the fan step is the climate fan
mode, quiet and turbo are switches. The tests below show the unit treats them as
independent flags and keeps the fan step underneath, so writing one key never
has to rewrite the others.

#### Quiet on/off alone (2026-09-23)

Question: if something writes only `{Quiet: 0}` (as a separate quiet switch
would), does `WdSpd` survive? Proto v2 unit, `Mod=4`, `tools/probe.py`, status
read about 5 s after each set:

| Time (CEST) | Sent | Reply | Status after |
|-------------|------|-------|--------------|
| 11:01:51 | `Pow=1 WdSpd=2` | `Pow=1 WdSpd=2` | `WdSpd=2 Quiet=0 Tur=0` |
| 11:02:11 | `Quiet=1` | `Quiet=1` | `WdSpd=2 Quiet=1 Tur=0` |
| 11:02:32 | `Quiet=0` | `Quiet=0` | `WdSpd=2 Quiet=0 Tur=0` (same 25 s later) |
| 11:03:04 | `Pow=0 WdSpd=0` | `Pow=0 WdSpd=0` | back to start |

- `WdSpd` keeps its step through quiet on and off, so `{Quiet: 0}` alone is
  safe on this unit.
- The unit accepts `Quiet=1` and reports back 1. Idle value is 0. Newer apps
  send `Quiet=2` (see [parameters.md](parameters.md#quiet-quiet)); whether 1
  holds for longer than 25 s was not tested here.
- `WdSpd` still reads the stored step while quiet is on.

#### Quiet and turbo together (2026-09-23)

Question: does the unit clear one flag when the other is switched on, or when
turbo is switched off on its own? Same unit and method as above:

| Time (CEST) | Sent | Status after |
|-------------|------|--------------|
| 11:48:53 | `Pow=1 WdSpd=2` | `WdSpd=2 Quiet=0 Tur=0` |
| 11:49:20 | `Tur=1` | `WdSpd=2 Quiet=0 Tur=1` |
| 11:49:39 | `Quiet=1` | `WdSpd=2 Quiet=1 Tur=1` (same 20 s later) |
| 11:50:15 | `Tur=0` | `WdSpd=2 Quiet=1 Tur=0` |
| 11:50:32 | `Pow=0 WdSpd=0 Quiet=0 Tur=0` | back to start |

- The unit clears neither flag: status reports quiet and turbo on at the same
  time, and turning turbo off leaves quiet on.
- Which one the fan actually follows while both are on was not measured; the
  protocol gives no fan-speed readback.

### Swing labels

Fixed vertical and horizontal positions were mapped from native app screenshots:

- Horizontal: Left, Left center, Center, Right center, Right + Full swing
- Vertical: Fixed upper through Fixed lower + Full swing
- Wire value **1 = full swing** on both axes

## Bind / discovery issues

### Scan works, bind times out

Observed on V3.4M-style firmware when scan and bind used **separate UDP
sockets**. Fix: `scan_then_bind()` sends both on one socket (same as greeclimate
session behaviour).

### Docker Home Assistant

Host networking is required for reliable UDP/7000 if HA runs in Docker. Bridge
mode may break broadcast discovery and sometimes unicast bind.

### Discovery vs setup

Network scan (broadcast) can succeed while manual setup (unicast bind to chosen
IP) fails if bind handshake timing or protocol version is wrong — these are
separate code paths; use `probe.py scan --bind` to isolate.

## Hide-when-missing validation

Entity discovery is driven by the **first successful status poll** after setup.
If a param is in the device's capability set but missing from that poll's
`cols`, no entity is created. Re-add the integration after firmware updates that
expose new parameters.

## Contributing new mappings

When adding support for a parameter:

1. Capture `probe.py status` output (discovery mode).
2. Confirm read values and test `probe.py set`.
3. Compare with the native app UI labels.
4. Document wire value → UI label mapping in [parameters.md](parameters.md).
5. Add a row to `tests/test_entity_discovery.py` if the param should create an
   entity on reference hardware.
