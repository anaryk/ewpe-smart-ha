# EWPE Smart — Home Assistant Integration

[![Tests](https://github.com/anaryk/ewpe-smart-ha/actions/workflows/tests.yml/badge.svg)](https://github.com/anaryk/ewpe-smart-ha/actions/workflows/tests.yml)
[![Validate](https://github.com/anaryk/ewpe-smart-ha/actions/workflows/validate.yml/badge.svg)](https://github.com/anaryk/ewpe-smart-ha/actions/workflows/validate.yml)
[![Lint](https://github.com/anaryk/ewpe-smart-ha/actions/workflows/lint.yml/badge.svg)](https://github.com/anaryk/ewpe-smart-ha/actions/workflows/lint.yml)
[![CodeQL](https://github.com/anaryk/ewpe-smart-ha/actions/workflows/codeql.yml/badge.svg)](https://github.com/anaryk/ewpe-smart-ha/actions/workflows/codeql.yml)
[![Bandit](https://github.com/anaryk/ewpe-smart-ha/actions/workflows/bandit.yml/badge.svg)](https://github.com/anaryk/ewpe-smart-ha/actions/workflows/bandit.yml)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
![version](https://img.shields.io/badge/version-0.1.1-blue)
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
  target temperature, fan speed (Auto / Low / Medium / High)
- 📊 **Indoor temperature sensor** — exposed separately for graphs and automations
- 🔍 **Manual IP setup or local network discovery**
- 🏠 **Multi-device support** — add as many units as you have, each gets its own
  device card in HA
- 🔒 **Encrypted communication** — uses the EWPE Smart AES-128 protocol
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
4. Add `https://github.com/anaryk/ewpe-smart-ha` with category
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
             ├── climate.py
             ├── config_flow.py
             ├── const.py
             ├── coordinator.py
             ├── device.py
             ├── manifest.json
             ├── protocol.py
             ├── sensor.py
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
4. The integration will run a bind handshake to obtain the device-specific
   encryption key, then start polling immediately.
5. Repeat for each additional unit. Each becomes its own device card in HA
   with one `climate.*` entity and one `sensor.*_indoor_temperature` entity.

> **Tip:** assign a static DHCP lease to each AC controller in your router so
> the IP doesn't change. If it does, simply reconfigure the entry with the new
> IP — the device key stays valid.

## Entities

### `climate.<your_unit_name>`

| Attribute | Behaviour |
|---|---|
| Power | On / Off via HVAC mode dropdown or `turn_on` / `turn_off` services |
| HVAC mode | Off / Auto / Cool / Heat / Dry / Fan only |
| Target temp | 16–30 °C, 1 °C steps |
| Current temp | Read from the unit's internal `TemSen` sensor |
| Fan speed | Auto / Low / Medium / High |

### `sensor.<your_unit_name>_indoor_temperature`

The same indoor temperature value as `climate.current_temperature`, exposed as
a separate sensor entity. Useful for long-term graphs in HA's energy/history
dashboards or for use in automations independently of the climate entity.

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

### "The device replied with an unexpected payload"

This usually means the bind handshake succeeded but the device sent a status
reply that doesn't fit the expected schema. Open an issue with the HA log
output (set the integration log level to debug — see below).

### Re-authentication required

If you've reset the AC controller (factory reset, firmware update, etc.) the
device-specific key stored by HA becomes invalid. HA will automatically prompt
for re-authentication; just click through and the bind will be repeated.

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

EWPE Smart devices speak a UDP/7000 protocol with AES-128 ECB encryption and
PKCS#7 padding. The protocol was reverse-engineered by
[tomikaa87/gree-remote](https://github.com/tomikaa87/gree-remote) and is also
implemented as an MQTT bridge by
[stas-demydiuk/ewpe-smart-mqtt](https://github.com/stas-demydiuk/ewpe-smart-mqtt).

This integration is a clean-room Python port of the protocol layer, structured
for testability: the `protocol.py` and `device.py` modules have **no Home
Assistant imports** and can be exercised by a plain pytest run.

## Running the test suite

If you want to hack on the integration:

```bash
git clone https://github.com/anaryk/ewpe-smart-ha
cd ewpe-smart-ha
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements_test.txt
pytest -v
```

The test suite uses an in-process mock UDP server (see `tests/mock_device.py`)
so no real device is required.

## Roadmap

- **Phase 2:** switch entities for sleep / turbo / quiet / X-fan / health /
  display light / energy save / fresh-air valve
- **Phase 3:** swing controls (up/down, left/right, and 4-way for cassettes)
- **Phase 4:** 8 °C frost-protection mode, child lock, lock-remote toggle

If a feature you need is missing, open an issue describing your unit (brand,
model, what the EWPE Smart app shows for it).

## Credits

- [tomikaa87/gree-remote](https://github.com/tomikaa87/gree-remote) — original
  protocol reverse engineering
- [stas-demydiuk/ewpe-smart-mqtt](https://github.com/stas-demydiuk/ewpe-smart-mqtt)
  — reference Node.js implementation
- [Species84720/ewpe_smart_ha](https://github.com/Species84720/ewpe_smart_ha)
  — earlier HA port targeting Ergo air purifiers (different device class)

## License

MIT — see [LICENSE](LICENSE).
