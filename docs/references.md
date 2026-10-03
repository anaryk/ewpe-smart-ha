# External references

Curated links for protocol reverse engineering, comparable integrations, and
this project's upstream history. Use **gree-remote** as the canonical wire-protocol
source; other projects may add higher-level semantics or different UX choices.

## Protocol reverse engineering

| Resource | What it provides |
|----------|------------------|
| [tomikaa87/gree-remote](https://github.com/tomikaa87/gree-remote) | Original UDP/7000 protocol RE — parameter keys, packet types, AES-ECB encryption. Start with the [README](https://github.com/tomikaa87/gree-remote/blob/master/README.md). |
| [stas-demydiuk/ewpe-smart-mqtt](https://github.com/stas-demydiuk/ewpe-smart-mqtt) | Node.js MQTT bridge for EWPE Smart; reference for status/cmd packet shape and parameter names. |
| [cmroche/greeclimate](https://github.com/cmroche/greeclimate) | Python Gree client used by HA core; bind session behaviour, JSON serialization, V2 GCM support. **Quiet=2 fix:** [issue #87](https://github.com/cmroche/greeclimate/issues/87). |
| [inwaar/gree-hvac-client](https://github.com/inwaar/gree-hvac-client) | Higher-level HVAC client with multi-level quiet/air modes — **not** the canonical wire spec; useful for comparing app-level semantics only. |

## Home Assistant integrations

| Resource | What it provides |
|----------|------------------|
| [Home Assistant — Gree](https://www.home-assistant.io/integrations/gree/) | Official core integration docs (broadcast discovery, climate + some switches). Does **not** support manual IP entry — a common reason to use ewpe-smart-ha. |
| [HA core `gree` source](https://github.com/home-assistant/core/tree/dev/homeassistant/components/gree) | Implementation of the official integration (uses greeclimate). |
| [p-monteiro/HomeAssistant-GreeClimateComponent-Rewrite](https://github.com/p-monteiro/HomeAssistant-GreeClimateComponent-Rewrite) | Community Gree rewrite with extended `GreeProp` coverage — useful parameter/enum reference. See [`aiogree/api.py`](https://github.com/p-monteiro/HomeAssistant-GreeClimateComponent-Rewrite/blob/e5ed1952102c104f0232ca816c87ed8bbd46c9d7/custom_components/gree_custom/aiogree/api.py) for wire keys and swing enums. |
| [Species84720/ewpe_smart_ha](https://github.com/Species84720/ewpe_smart_ha) | Earlier HA port targeting Ergo air purifiers (different device class, same family of protocol). |

## This repository

| Resource | What it provides |
|----------|------------------|
| [anaryk/ewpe-smart-ha](https://github.com/anaryk/ewpe-smart-ha) | Upstream integration repo (manual IP, hide-when-missing entities, probe tool). |
| [Issue tracker](https://github.com/anaryk/ewpe-smart-ha/issues) | Bugs and feature requests. |
| [PR #13 — hybrid bind / V2](https://github.com/anaryk/ewpe-smart-ha/pull/13) | Scan+bind on one UDP socket; auto-detect and persist `protocol_version`. |
| [PR #14 — switch entities](https://github.com/anaryk/ewpe-smart-ha/pull/14) | Phase 2 auxiliary switches (draft). |
| [PR #15 — silent commands](https://github.com/anaryk/ewpe-smart-ha/pull/15) | `Buzzer_ON_OFF` append on HA commands (draft; later reverted on fork — see [hardware-notes.md](hardware-notes.md)). |

## Installation & tooling

| Resource | What it provides |
|----------|------------------|
| [HACS](https://hacs.xyz/) | Home Assistant Community Store — recommended install path for custom integrations. |
| [HACS integration docs](https://www.home-assistant.io/docs/development/integration_manifest/) | HA manifest / integration structure reference. |
| [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component) | Test harness used by this repo's CI (see `requirements_test.txt`). |

## How we use these sources

| Topic | Primary source | Secondary |
|-------|----------------|-----------|
| Wire keys and 0/1 semantics | [gree-remote README](https://github.com/tomikaa87/gree-remote/blob/master/README.md) | [gree_custom `api.py`](https://github.com/p-monteiro/HomeAssistant-GreeClimateComponent-Rewrite/blob/e5ed1952102c104f0232ca816c87ed8bbd46c9d7/custom_components/gree_custom/aiogree/api.py) |
| Bind handshake / V2 GCM | [greeclimate](https://github.com/cmroche/greeclimate), this repo's `protocol.py` | [ewpe-smart-mqtt](https://github.com/stas-demydiuk/ewpe-smart-mqtt) |
| Entity naming & hide-when-missing | This repo's conventions | [HA Gree switches](https://www.home-assistant.io/integrations/gree/) for UX comparison |
| Hardware validation | `tools/probe.py` + native EWPE Smart app | Live unit snapshots in [hardware-notes.md](hardware-notes.md) |

When a secondary source disagrees with gree-remote (e.g. multi-level `Quiet` values),
prefer **probe output on real hardware** over library abstractions.
