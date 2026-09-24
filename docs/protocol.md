# Wire protocol

EWPE Smart WiFi controllers speak a UDP binary protocol on port **7000**, with
AES-encrypted inner payloads.

This integration implements V1 and V2 in `custom_components/ewpe_smart/protocol.py`.

**See also:** [references.md](references.md) for the full list of protocol and
integration sources. Primary references:

- [tomikaa87/gree-remote](https://github.com/tomikaa87/gree-remote) — canonical
  parameter keys and packet types ([README](https://github.com/tomikaa87/gree-remote/blob/master/README.md))
- [stas-demydiuk/ewpe-smart-mqtt](https://github.com/stas-demydiuk/ewpe-smart-mqtt) —
  EWPE Smart MQTT bridge
- [cmroche/greeclimate](https://github.com/cmroche/greeclimate) — bind session
  behaviour and V2 GCM (used by [HA core Gree](https://www.home-assistant.io/integrations/gree/))

## Transport

| Setting | Value |
|---------|-------|
| Protocol | UDP |
| Port | 7000 (default) |
| Timeout | 5 s (requests), 10 s (bind) |

## Two encryption versions

### V1 — AES-128 ECB (original firmware)

- Generic key (scan/bind only): `a3K8Bx%2r8Y7#xDh`
- PKCS#7 padding, base64 ciphertext in outer `pack` field
- Outer envelope: `{"cid":"app","i":0|1,"t":"pack","uid":0,"pack":"<b64>"}`
  - `i: 1` when encrypting with generic key (scan/bind)
  - `i: 0` when encrypting with device key (status/cmd)

### V2 — AES-128 GCM (newer firmware)

- Generic key: `{yxAHAY_Lm6pbC/<`
- Fixed nonce: `T@xDGIgZQl^c\x13` (12 bytes)
- AAD: `qualcomm-test`
- Outer envelope adds `"tag": "<b64 16-byte GCM tag>"` next to `pack`
- Presence of `tag` in a reply indicates V2

Commercial U-Match, XE7A-style controllers, and recent split units often use V2.

## Packet types

### Scan (plaintext)

**Request** (unicast or broadcast):

```json
{"t": "scan"}
```

**Reply** (`t: dev`):

```json
{
  "t": "dev",
  "cid": "AA:BB:CC:DD:EE:FF",
  "name": "Living room AC",
  "brand": "Daitsu",
  "model": "…",
  "ver": "V3.4M"
}
```

MAC may appear as `cid` or `mac`.

### Bind (generic key, encrypted)

**Request:**

```json
{"t": "bind", "mac": "AA:BB:…", "uid": 0}
```

**Reply** (`t: bindok`):

```json
{"t": "bindok", "key": "16-byte-string"}
```

The returned `key` is used for all subsequent status/cmd traffic.

**Important:** scan and bind should share one UDP socket on many firmware
versions. See `scan_then_bind()` in `protocol.py`.

### Status (device key, encrypted)

**Request:**

```json
{"t": "status", "mac": "AA:BB:…", "cols": ["Pow", "Mod", "SetTem", …]}
```

**Reply** (`t: dat`):

```json
{
  "t": "dat",
  "cols": ["Pow", "Mod", "SetTem"],
  "dat": [1, 1, 22]
}
```

Devices typically echo only the columns they support. Requesting unknown cols
may omit them from the reply entirely.

### Command (device key, encrypted)

**Request:**

```json
{"t": "cmd", "mac": "AA:BB:…", "opt": ["SetTem"], "p": [24]}
```

**Reply** (`t: res`):

```json
{"t": "res", "opt": ["SetTem"], "val": [24]}
```

Some firmware echoes values in `p` instead of `val`. `parse_cmd_reply()` handles
both.

Multiple parameters can be set in one packet:

```json
{"opt": ["WdSpd", "Quiet", "Tur"], "p": [3, 0, 0]}
```

## Bind strategy (hybrid V1/V2)

`scan_then_bind()`:

1. Detect protocol from scan reply envelope (V2 if `tag` present).
2. Try bind on detected version first, then alternate on timeout.
3. Persist working version in the HA config entry.

During runtime, `_send_with_version_fallback()` retries failed requests on the
alternate version and updates stored version when successful.

## Temperature encoding

Indoor (`TemSen`) and outdoor (`OutEnvTem`) sensors store **raw = °C + 40** on
the wire. The integration applies offset −40 in `get_status()` before entities
consume values.

Example: wire value 61 → 21 °C.

Plausible range checks discard garbage readings (indoor: −10…60 after decode;
outdoor: −40…60 after decode).

## JSON serialization

Inner payloads use compact JSON (`separators=(",", ":")`) matching greeclimate /
Gree+ app behaviour — spacing matters for some firmware.

## Security notes

- Generic keys are public (same for all units of a protocol generation).
- Device keys are unique per controller and stored in HA config entries.
- All control is local LAN only; no cloud relay in this integration.

## Error types

| Exception | Meaning |
|-----------|---------|
| `EwpeTimeout` | No UDP reply within timeout |
| `EwpeAuthError` | Decryption failed (wrong/stale key) |
| `EwpeProtocolError` | Unexpected `t` field or malformed body |
| `EwpeError` | Base class / device not bound |
