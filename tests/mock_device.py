"""A tiny in-process UDP server that simulates an EWPE Smart device.

Used by the test suite to exercise the full client → server → client cycle
without touching the network. Can speak either the V1 (AES-ECB) or V2
(AES-GCM) wire format depending on ``protocol_version``.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from custom_components.ewpe_smart.const import (
    GENERIC_KEY,
    GENERIC_KEY_V2,
    PROTO_V1,
    PROTO_V2,
)
from custom_components.ewpe_smart.protocol import (
    decrypt,
    decrypt_v2,
    encrypt,
    encrypt_v2,
)


class MockEwpeProtocol(asyncio.DatagramProtocol):
    """Simulates one device. Tracks received commands for test assertions."""

    def __init__(
        self,
        mac: str = "AA:BB:CC:DD:EE:FF",
        name: str = "MockAC",
        device_key: bytes = b"abcdefghijklmnop",
        status: dict[str, int] | None = None,
        misbehave: str | None = None,
        protocol_version: int = PROTO_V1,
    ) -> None:
        self.mac = mac
        self.name = name
        self.device_key = device_key
        self.status: dict[str, int] = status or {
            "Pow": 1,
            "Mod": 1,
            "SetTem": 22,
            "TemUn": 0,
            "WdSpd": 0,
            "TemSen": 65,  # raw value before -40 offset → 25 °C
        }
        self.misbehave = misbehave
        self.protocol_version = protocol_version
        self.received_commands: list[dict[str, Any]] = []
        self.transport: asyncio.DatagramTransport | None = None

    @property
    def _generic_key(self) -> bytes:
        return GENERIC_KEY_V2 if self.protocol_version == PROTO_V2 else GENERIC_KEY

    def _decrypt_inbound(self, envelope: dict[str, Any]) -> dict[str, Any]:
        key = self._generic_key if envelope.get("i") == 1 else self.device_key
        if "tag" in envelope:
            return decrypt_v2(envelope["pack"], envelope["tag"], key)
        return decrypt(envelope["pack"], key)

    def _build_envelope(self, reply: dict[str, Any]) -> dict[str, Any]:
        out_key = (
            self.device_key if reply.get("t") in {"dat", "res"} else self._generic_key
        )
        i_field = 0 if reply.get("t") in {"dat", "res"} else 1
        if self.protocol_version == PROTO_V2:
            pack, tag = encrypt_v2(reply, out_key)
            return {
                "cid": self.mac,
                "i": i_field,
                "t": "pack",
                "uid": 0,
                "pack": pack,
                "tag": tag,
            }
        return {
            "cid": self.mac,
            "i": i_field,
            "t": "pack",
            "uid": 0,
            "pack": encrypt(reply, out_key),
        }

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if self.misbehave == "silent":
            return
        if self.misbehave == "garbage":
            assert self.transport is not None
            self.transport.sendto(b"not-json", addr)
            return

        envelope = json.loads(data.decode("utf-8"))
        if "pack" in envelope:
            inner = self._decrypt_inbound(envelope)
        else:
            # Unencrypted broadcast/unicast scan
            inner = envelope

        reply = self._build_reply(inner)
        if reply is None:
            return

        out = self._build_envelope(reply)
        assert self.transport is not None
        self.transport.sendto(
            json.dumps(out, separators=(",", ":")).encode("utf-8"),
            addr,
        )

    def _build_reply(self, inner: dict[str, Any]) -> dict[str, Any] | None:
        t = inner.get("t")
        if t == "scan":
            return {
                "t": "dev",
                "cid": self.mac,
                "mac": self.mac,
                "name": self.name,
                "brand": "Daitsu",
                "model": "MockAC-1",
                "vender": "Gree",
                "ver": "V1.0.0",
            }
        if t == "bind":
            return {
                "t": "bindok",
                "mac": self.mac,
                "key": self.device_key.decode("utf-8"),
            }
        if t == "status":
            requested = inner.get("cols") or list(self.status.keys())
            cols = [c for c in requested if c in self.status]
            return {
                "t": "dat",
                "mac": self.mac,
                "cols": cols,
                "dat": [self.status[c] for c in cols],
            }
        if t == "cmd":
            opt = inner.get("opt") or []
            values = inner.get("p") or []
            self.received_commands.append({"opt": opt, "p": values})
            for k, v in zip(opt, values, strict=False):
                self.status[k] = v
            return {
                "t": "res",
                "mac": self.mac,
                "opt": opt,
                "val": values,
            }
        return None


async def start_mock_device(**kwargs: Any) -> tuple[MockEwpeProtocol, int]:
    """Spin up a mock device on localhost and return ``(protocol, port)``."""
    loop = asyncio.get_running_loop()
    protocol = MockEwpeProtocol(**kwargs)
    transport, _ = await loop.create_datagram_endpoint(
        lambda: protocol, local_addr=("127.0.0.1", 0)
    )
    sockname = transport.get_extra_info("sockname")
    return protocol, sockname[1]
