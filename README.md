# EWPE Smart — Home Assistant Integration

[![Tests](https://github.com/anaryk/ewpe-smart-ha/actions/workflows/tests.yml/badge.svg)](https://github.com/anaryk/ewpe-smart-ha/actions/workflows/tests.yml)
[![Validate](https://github.com/anaryk/ewpe-smart-ha/actions/workflows/validate.yml/badge.svg)](https://github.com/anaryk/ewpe-smart-ha/actions/workflows/validate.yml)
[![Lint](https://github.com/anaryk/ewpe-smart-ha/actions/workflows/lint.yml/badge.svg)](https://github.com/anaryk/ewpe-smart-ha/actions/workflows/lint.yml)
[![CodeQL](https://github.com/anaryk/ewpe-smart-ha/actions/workflows/codeql.yml/badge.svg)](https://github.com/anaryk/ewpe-smart-ha/actions/workflows/codeql.yml)
[![Bandit](https://github.com/anaryk/ewpe-smart-ha/actions/workflows/bandit.yml/badge.svg)](https://github.com/anaryk/ewpe-smart-ha/actions/workflows/bandit.yml)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
![version](https://img.shields.io/badge/version-0.3.0-blue)
![license](https://img.shields.io/badge/license-MIT-green.svg)

Local-polling Home Assistant integration for air conditioners controlled via the
**EWPE Smart** mobile app — works with **Daitsu**, **Gree**, **Cooper&Hunter**,
**Sinclair**, **EcoAir** and **ProKlima** units that share the same WiFi
controller protocol.

Built specifically because the official `gree` integration in Home Assistant
core sometimes fails to discover commercial cassette units (Daitsu in
particular). This integration **lets you enter the IP address manually** and
talks to the unit over UDP/7000 directly — no MQTT broker, no extra processes.

## Features

- 🌡️ **Climate entity** — power, HVAC mode (Auto / Cool / Heat / Dry / Fan only),
  target temperature, current indoor temperature, fan mode (auto and all five
  fixed steps)
- 💨 **Quiet and Turbo switches** when the firmware exposes them
- ↔️ **Swing selects** — horizontal and vertical louver positions (including
  cassette multi-zone keys when present)
- 🔌 **Switch entities** — sleep modes, energy save, beeper, X-Fan, health,
  display, timers, child lock, auto clean, UV-C, and more (**one switch per wire
  key** the device returns, so overlapping names like `BuzzerCtrl` and
  `Buzzer_ON_OFF` stay separate)
- 📊 **Sensors** — indoor/outdoor temperature, humidity (`Wet`), drain water
  (`DwatSen`), PM2.5, fault codes,
  compressor diagnostics, filter status, and metadata fields when echoed
- 🔢 **Number entities** — timer countdowns, unoccupied-off delay, sleep-curve
  temperature steps
- 🔔 **Binary sensors** — HEPA replacement, motion, drain pump, timer active, …
- 🔍 **Permissive discovery** — polls a 140-key wire catalog on setup/reload;
  creates entities only for parameters the unit actually supports
- 🔍 **Manual IP setup or local network discovery**
- 🏠 **Multi-device support** — add as many units as you have, each gets its own
  device card in HA
- 🔒 **Encrypted communication** — AES-ECB (V1) or AES-GCM (V2), auto-detected
- ⚙️ **Configurable polling interval** (10–300 seconds, default 30)
- 🌐 **Czech and English UI translations**
- ✅ **Fully local** — no cloud, no third-party services

## Requirements

| Requirement | Details |
|---|---|
| Home Assistant | ≥ 2024.8 |
| Python package | `cryptography` (already shipped with Home Assistant) |
| Network | HA must be able to reach the AC unit over UDP port 7000 |
| Device setup | The AC must be already connected to your WiFi via the **EWPE Smart** app |

## Installation

### Option A — HACS (recommended)

1. Make sure you have [HACS](https://hacs.xyz/) installed.
2. In Home Assistant, open **HACS → Integrations**.
3. Click the **⋮** menu (top-right) → **Custom repositories**.
4. Add `https://github.com/rasmusbe/ewpe-smart-ha` with category
   **Integration** and click **Add**.
5. Search for **EWPE Smart** in the HACS Integrations list and click
   **Download**.
6. Restart Home Assistant.

### Option B — Manual

1. SSH into your HA host (or use the Samba / File Editor add-on).
2. Inside your `config/` directory, create the folder
   `config/custom_components/` if it does not exist.
3. Copy the `custom_components/ewpe_smart/` folder from this repo into
   `config/custom_components/ewpe_smart/`. The result should look like:
   ```
   config/
     └── custom_components/
         └── ewpe_smart/
             ├── __init__.py
             ├── binary_sensor.py
             ├── climate.py
             ├── config_flow.py
             ├── const.py
             ├── coordinator.py
             ├── device.py
             ├── manifest.json
             ├── number.py
             ├── params_catalog.py
             ├── protocol.py
             ├── select.py
             ├── sensor.py
             ├── switch.py
             ├── strings.json
             └── translations/
                 ├── cs.json
                 └── en.json
   ```
4. Restart Home Assistant.

## Setup

1. In Home Assistant, go to **Settings → Devices & Services → Add Integration**.
2. Search for **EWPE Smart** and select it.
3. Choose how to add the device:
   - **Enter IP address manually** — recommended; fastest path. Type the IP of
     the AC's WiFi controller (find it in your router's DHCP leases or in the
     EWPE Smart app under device settings) and an optional friendly name.
   - **Scan local network** — sends a UDP broadcast and lists every responding
     device. May not find your unit if HA is on a different subnet/VLAN, in
     which case fall back to manual entry.
4. The integration runs a bind handshake to obtain the device-specific
   encryption key, then polls the full parameter catalog (in batches) to learn
   which wire keys your firmware supports.
5. Repeat for each additional unit. Each unit becomes its own device card with a
   `climate.*` entity plus whatever switches, selects, sensors, numbers, and
   binary sensors your hardware exposes.

> **Tip:** assign a static DHCP lease to each AC controller in your router so
> the IP doesn't change. If it does, reconfigure the entry with the new IP — the
> device key usually stays valid.

> **After upgrading:** reload the integration entry (or restart HA) so discovery
> runs again. Remove orphaned entities from older versions (for example a single
> `switch.beeper`) if they no longer update.

## Entities

Entity creation is **hide-when-missing**: only wire keys present in the device's
status reply get entities. The exact set varies by model and firmware.

| Platform | Examples |
|----------|----------|
| `climate` | Power, HVAC mode, target/current temperature |
| `select` | Horizontal/vertical swing |
| `switch` | Quiet, turbo, sleep (`SmartSlpMod`, `SlpMod`, `SwhSlp`), beeper (`BuzzerCtrl`, `Buzzer_ON_OFF`), energy save, child lock, auto clean, … |
| `sensor` | Indoor/outdoor temp, humidity (`Wet`), drain water (`DwatSen`), PM2.5, faults, metadata when returned |
| `number` | Timer minutes left, sleep-curve steps, unoccupied-off time |
| `binary_sensor` | Replace HEPA, motion, drain pump, has timer |

Switch names include the wire key (for example **Beeper (BuzzerCtrl)**) so you
can tell similar-looking controls apart and see which one actually works on your
unit.

Full parameter and entity reference: **[docs/parameters.md](docs/parameters.md)**  
Architecture and discovery flow: **[docs/integration.md](docs/integration.md)**

### `climate.<your_unit_name>`

| Attribute | Behaviour |
|---|---|
| Power | On / Off via HVAC mode dropdown or `turn_on` / `turn_off` services |
| HVAC mode | Off / Auto / Cool / Heat / Dry / Fan only |
| Target temp | 16–30 °C, 1 °C steps |
| Current temp | Read from the unit's internal `TemSen` sensor |
| Fan mode | Auto, low, medium low, medium, medium high, high (`WdSpd` 0–5) |

### `sensor.<your_unit_name>_indoor_temperature`

Same value as `climate.current_temperature`, exposed separately for history
graphs and automations.

## Options

After setup, click **Configure** on the device card to change:

- **Polling interval** — how often HA reads the unit's state (10–300 s,
  default 30 s). Lower = more responsive UI but more network traffic.

## Troubleshooting

### "Could not reach the device on the supplied IP"

- Verify the AC is online: try `ping <ip>` from your HA host.
- Check that nothing is blocking UDP/7000 between HA and the AC (firewall,
  VLAN ACL, mDNS reflector misconfig, …).
- If HA runs in a Docker container, ensure it uses **host networking**.
  Bridge networking will swallow UDP broadcast and may also break unicast in
  some configurations.

### "The device refused the connection on UDP 7000"

The unit answered with an ICMP port unreachable, so it is powered on and
routable but has nothing bound to UDP/7000. This is not a firewall, a wrong IP
or a protocol-version mismatch: the device itself said "no listener here".

Recent Gree/Tosot/Sinclair wifi modules (firmware 2.x) ship with local control
disabled, and the vendor app then runs everything through the cloud. Things to
try, in order:

1. Put the module in AP mode (usually the display's `Mode` + `WiFi` key
   combination, see your manual) and re-pair the unit with the vendor app on
   the local network. Some modules re-enable UDP/7000 after a fresh pairing.
2. Check the vendor app for a "LAN control" / "local mode" toggle.
3. Verify with a packet capture that a broadcast `{"t":"scan"}` gets any reply
   at all. Zero replies means the module keeps local control off and no
   integration can reach it.

If none of that helps, the module has to be replaced with one that speaks the
local protocol. There is nothing the integration can do from the HA side.

### Status poll times out or few entities appear

Some firmware stops responding when too many parameters are requested in one
packet. The integration batches discovery automatically; if problems persist,
use `tools/probe.py` (see below) with `--export-cols` and open an issue with
your model and firmware version (`ver` from the device reply).

### "The device replied with an unexpected payload"

Usually means the bind handshake succeeded but a status reply did not match the
expected schema. Open an issue with debug logs (see below).

### The device changed IP address

When a poll times out, the integration broadcasts a scan and follows the unit to
its new address if the MAC matches, then writes that address back to the config
entry. If broadcast does not reach the device (routed VLAN, Docker bridge
networking), use **Settings → Devices & Services → EWPE Smart → Reconfigure** and
type the new IP manually. A DHCP reservation for the AC avoids the problem
altogether.

### Re-authentication required

If you've reset the AC controller (factory reset, firmware update, etc.) the
stored device key may become invalid. HA will prompt for re-authentication;
submit the flow to re-run bind.

### Download diagnostics

When opening an issue, attach the diagnostics file: **Settings → Devices &
services → EWPE Smart → ⋮ → Download diagnostics**. It includes the detected
protocol version, model/firmware info and the last status reply. The device
key and MAC address are redacted.

### Enable debug logging

Add this to your `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.ewpe_smart: debug
```

Then restart HA and reproduce the issue.

## Protocol notes

EWPE Smart devices speak UDP/7000 with AES encryption (V1 ECB or V2 GCM). The
protocol was reverse-engineered by
[tomikaa87/gree-remote](https://github.com/tomikaa87/gree-remote) and is also
implemented as an MQTT bridge by
[stas-demydiuk/ewpe-smart-mqtt](https://github.com/stas-demydiuk/ewpe-smart-mqtt).

This integration is a clean-room Python port of the protocol layer, structured
for testability: the `protocol.py` and `device.py` modules have **no Home
Assistant imports** and can be exercised by a plain pytest run. The wire-key
catalog lives in
[`custom_components/ewpe_smart/data/wire_params.json`](custom_components/ewpe_smart/data/wire_params.json)
and is loaded by `params_catalog.py`.

## Development

### Tests

```bash
git clone https://github.com/rasmusbe/ewpe-smart-ha
cd ewpe-smart-ha
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements_test.txt
pytest -v
```

No real device is required — see `tests/mock_device.py`.

### Probe CLI

Talk to a unit on the LAN without HA:

```bash
pip install cryptography
python3 tools/probe.py scan <ip> --decrypt --bind
python3 tools/probe.py status <ip> --key '<key>' --mac '<mac>' --export-cols
```

See **[docs/probe.md](docs/probe.md)** for full usage (set commands, protocol
version override, batched discovery).

## Roadmap

- [x] Switch entities for auxiliary features
- [x] Swing selects
- [x] Extended sensors, numbers, binary sensors, full-catalog discovery
- [ ] Options UI to trim noisy entities per installation
- [ ] Documented silent-command behaviour where firmware supports it

If something your app shows is missing from HA, open an issue with brand, model,
firmware version, and `probe.py status --export-cols` output when possible.

## Credits

- [tomikaa87/gree-remote](https://github.com/tomikaa87/gree-remote) — original
  protocol reverse engineering
- [stas-demydiuk/ewpe-smart-mqtt](https://github.com/stas-demydiuk/ewpe-smart-mqtt)
  — reference Node.js implementation
- [Species84720/ewpe_smart_ha](https://github.com/Species84720/ewpe_smart_ha)
  — earlier HA port targeting Ergo air purifiers (different device class)

## License

MIT — see [LICENSE](LICENSE).
