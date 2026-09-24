# Probe tool (`tools/probe.py`)

Standalone CLI for talking to a real EWPE Smart device without Home Assistant.
Use it on the **same machine that runs HA** (or any host on the same LAN with
UDP/7000 reachability).

Comparable tools: [ewpe-smart-mqtt](https://github.com/stas-demydiuk/ewpe-smart-mqtt)
(Node.js), [greeclimate](https://github.com/cmroche/greeclimate) CLI patterns,
[gree-remote](https://github.com/tomikaa87/gree-remote) protocol docs. See
[references.md](references.md).

## Setup

```bash
cd ewpe-smart-ha
python3 -m venv .venv
source .venv/bin/activate
pip install cryptography
```

## Commands

### Scan / discover (legacy syntax)

```bash
python3 tools/probe.py 192.168.1.50 --decrypt
```

Equivalent subcommand:

```bash
python3 tools/probe.py scan 192.168.1.50 --decrypt
```

Prints protocol version (V1/V2) and decrypted device info (MAC, name, model).

### Scan + bind

```bash
python3 tools/probe.py scan 192.168.1.50 --decrypt --bind
```

Runs the full handshake on one UDP socket — mirrors what HA does during setup.
On success, note the device key for subsequent commands.

### Status (discovery mode — default)

Requests **all** `DISCOVERY_PARAMS` (runtime params + discovery-only params):

```bash
python3 tools/probe.py status 192.168.1.50 \
  --key 'YOUR_DEVICE_KEY' \
  --mac 'AA:BB:CC:DD:EE:FF'
```

Prints every `col = value` pair returned, lists supported switches, and flags
discovery-only params present in the reply.

### Status (runtime mode)

Requests only `STATUS_PARAMS` — same set the integration polls:

```bash
python3 tools/probe.py status 192.168.1.50 \
  --key 'YOUR_DEVICE_KEY' \
  --mac 'AA:BB:CC:DD:EE:FF' \
  --runtime
```

Use this to verify what HA sees after entity discovery.

### Status (custom columns)

Request specific wire keys only — useful when a param accepts `set` but is
omitted from full discovery `cols` (for example `BuzzerCtrl`):

```bash
python3 tools/probe.py status 192.168.1.50 \
  --key 'YOUR_DEVICE_KEY' \
  --mac 'AA:BB:CC:DD:EE:FF' \
  BuzzerCtrl Buzzer_ON_OFF
```

Keys the firmware does not expose in status are listed as `not in reply`.

### Set parameters

```bash
python3 tools/probe.py set 192.168.1.50 \
  --key 'YOUR_DEVICE_KEY' \
  --mac 'AA:BB:CC:DD:EE:FF' \
  Quiet=2 WdSpd=0 Tur=0
```

Multiple `Param=value` pairs are sent in one `cmd` packet.

### Force protocol version

```bash
python3 tools/probe.py status 192.168.1.50 \
  --key '…' --mac '…' --version 2
```

Default is auto-detect (try V1 then V2, or vice versa based on envelope).

## Getting the device key from Home Assistant

1. **Settings → Devices & Services → EWPE Smart → Configure device**
2. Or inspect `.storage/core.config_entries` for the `ewpe_smart` entry `key`
   field (advanced).

After a factory reset, re-bind via HA reauth or `scan --bind`.

## Helper scripts

| Script | Purpose |
|--------|---------|
| `tools/probe_common.sh` | Shared env vars for local probe scripts |
| `tools/probe_device.local.sh.example` | Template for device-specific probe wrapper |
| `tools/probe_wind_speed_experiment.sh` | Wind speed / quiet / turbo experiments |
| `tools/probe_wind_speed_memory_experiment.sh` | Whether WdSpd persists under quiet/turbo |

Copy `.example` files locally; do not commit IPs or keys.

## Relationship to the integration

| Probe step | HA equivalent |
|------------|---------------|
| `scan --decrypt` | Discovery / unicast scan in config flow |
| `scan --bind` | `EwpeDevice.bind()` |
| `status --runtime` | Coordinator poll |
| `set Param=value` | Entity write via `set_state()` |

`probe.py` duplicates `STATUS_PARAMS` / `DISCOVERY_PARAMS` from `const.py` with
a "keep in sync" comment — it does not import Home Assistant.

## Typical workflow for new parameters

1. Extend `DISCOVERY_PARAMS` in `const.py` and `probe.py` if adding candidates.
2. Run `probe.py status` and capture the full snapshot.
3. Build a mapping table: wire key → platform → entity type.
4. Implement entities with hide-when-missing semantics.
5. Validate with `probe.py set` and HA reload.

See [hardware-notes.md](hardware-notes.md) for unit-specific findings.
