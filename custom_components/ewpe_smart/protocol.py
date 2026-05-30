"""Low-level EWPE Smart / Gree wire protocol.

This module deliberately avoids any ``homeassistant`` imports so that it can be
exercised by a plain pytest run without spinning up Home Assistant.

Two on-the-wire formats are supported:

- **V1** — original Gree firmware. AES-128 ECB + PKCS#7 padding. The envelope
  carries a single ``pack`` field with the base64 ciphertext.
- **V2** — newer firmware (commercial U-Match, XE7A controllers, recent split
  units). AES-128 GCM. The envelope carries ``pack`` (ciphertext) AND ``tag``
  (16-byte GCM auth tag), each base64-encoded. Uses a different generic key
  during the bind handshake.

The version is detected automatically from the reply: a ``tag`` field next to
``pack`` flags V2.

Wire format reference:
- https://github.com/tomikaa87/gree-remote
- https://github.com/cmroche/greeclimate
- https://github.com/stas-demydiuk/ewpe-smart-mqtt
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import socket
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .const import (
    BUZZER_SILENT,
    DEFAULT_BIND_TIMEOUT,
    DEFAULT_TIMEOUT,
    GCM_AAD,
    GCM_NONCE,
    GENERIC_KEY,
    GENERIC_KEY_V2,
    PARAM_BUZZER_ON_OFF,
    PROTO_V1,
    PROTO_V2,
)

_LOGGER = logging.getLogger(__name__)

_BLOCK_BITS = 128  # AES block size in bits, used by PKCS#7 padder
_BLOCK_BYTES = _BLOCK_BITS // 8
_GCM_TAG_BYTES = 16


class EwpeError(Exception):
    """Base exception for EWPE Smart protocol failures."""


class EwpeTimeout(EwpeError):
    """Raised when the device does not reply within the timeout."""


class EwpeProtocolError(EwpeError):
    """Raised when the reply has the wrong type or cannot be parsed."""


class EwpeAuthError(EwpeError):
    """Raised when a reply cannot be decrypted with the supplied key."""


def append_silent_buzzer(opt: list[str], p: list[int]) -> None:
    """Append ``Buzzer_ON_OFF=1`` to a cmd packet when not already present."""
    if PARAM_BUZZER_ON_OFF not in opt:
        opt.append(PARAM_BUZZER_ON_OFF)
        p.append(BUZZER_SILENT)


def parse_cmd_reply(reply: dict[str, Any]) -> dict[str, int]:
    """Build ``{opt: value}`` from a ``t: res`` packet.

    Some firmware echoes values in ``val``; others reuse ``p`` (as in the request).
    """
    if reply.get("t") != "res":
        raise EwpeProtocolError(f"Unexpected cmd reply: {reply!r}")
    opt = reply.get("opt")
    if not isinstance(opt, list):
        raise EwpeProtocolError(f"Cmd reply is malformed: {reply!r}")
    values = reply.get("val")
    if not isinstance(values, list):
        values = reply.get("p")
    if not isinstance(values, list):
        raise EwpeProtocolError(f"Cmd reply is malformed: {reply!r}")
    return dict(zip(opt, values, strict=False))


def _aes_ecb(key: bytes) -> Cipher:
    # ECB is mandated by the V1 device protocol — the wire format predates
    # modern cipher modes. V2 uses GCM via AESGCM below.
    return Cipher(algorithms.AES(key), modes.ECB())  # nosec B305


def _json_bytes(payload: dict[str, Any]) -> bytes:
    """Serialize inner payloads like greeclimate / the Gree+ app (spaced JSON)."""
    return json.dumps(payload).encode("utf-8")


def _parse_json_bytes(data: bytes) -> dict[str, Any]:
    """Parse decrypted JSON, ignoring trailing padding bytes some firmware adds."""
    text = data.decode("utf-8", errors="replace")
    last = text.rfind("}")
    if last >= 0:
        text = text[: last + 1]
    return json.loads(text)


def encrypt(payload: dict[str, Any], key: bytes = GENERIC_KEY) -> str:
    """V1: AES-128 ECB encrypt ``payload`` and return base64 ASCII."""
    plaintext = _json_bytes(payload)
    padder = padding.PKCS7(_BLOCK_BITS).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = _aes_ecb(key).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ciphertext).decode("ascii")


def decrypt(ciphertext: str, key: bytes = GENERIC_KEY) -> dict[str, Any]:
    """V1: Decrypt a base64 AES-128 ECB blob into a JSON object."""
    raw = base64.b64decode(ciphertext)
    if len(raw) == 0 or len(raw) % _BLOCK_BYTES != 0:
        raise EwpeAuthError("Ciphertext length is not a multiple of block size")
    decryptor = _aes_ecb(key).decryptor()
    decoded_padded = decryptor.update(raw) + decryptor.finalize()
    unpadder = padding.PKCS7(_BLOCK_BITS).unpadder()
    try:
        decoded = unpadder.update(decoded_padded) + unpadder.finalize()
    except ValueError as err:
        raise EwpeAuthError("Failed to decrypt payload") from err
    try:
        return _parse_json_bytes(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise EwpeAuthError("Decrypted payload is not valid JSON") from err


def encrypt_v2(payload: dict[str, Any], key: bytes = GENERIC_KEY_V2) -> tuple[str, str]:
    """V2: AES-128 GCM encrypt ``payload`` → ``(pack_b64, tag_b64)``."""
    plaintext = _json_bytes(payload)
    aesgcm = AESGCM(key)
    ct_with_tag = aesgcm.encrypt(GCM_NONCE, plaintext, GCM_AAD)
    ciphertext = ct_with_tag[:-_GCM_TAG_BYTES]
    tag = ct_with_tag[-_GCM_TAG_BYTES:]
    return (
        base64.b64encode(ciphertext).decode("ascii"),
        base64.b64encode(tag).decode("ascii"),
    )


def decrypt_v2(
    pack_b64: str, tag_b64: str, key: bytes = GENERIC_KEY_V2
) -> dict[str, Any]:
    """V2: Decrypt a base64 AES-128 GCM (pack, tag) pair into a JSON object."""
    try:
        ciphertext = base64.b64decode(pack_b64)
        tag = base64.b64decode(tag_b64)
    except (ValueError, TypeError) as err:
        raise EwpeAuthError("V2 payload is not valid base64") from err
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(GCM_NONCE, ciphertext + tag, GCM_AAD)
    except InvalidTag as err:
        raise EwpeAuthError("V2 GCM auth tag mismatch (wrong key)") from err
    text = plaintext.decode("utf-8", errors="replace")
    # Some V2 firmwares pad the JSON with trailing bytes past the final '}'.
    last = text.rfind("}")
    if last >= 0:
        text = text[: last + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError as err:
        raise EwpeAuthError("Decrypted V2 payload is not valid JSON") from err


def _outer_packet(
    inner: dict[str, Any],
    key: bytes,
    version: int = PROTO_V1,
    *,
    tcid: str = "",
) -> bytes:
    """Wrap ``inner`` in the outer envelope and serialise to bytes."""
    device_tcid = tcid or str(inner.get("mac", ""))
    if version == PROTO_V2:
        pack, tag = encrypt_v2(inner, key)
        envelope: dict[str, Any] = {
            "cid": "app",
            "i": 1 if key == GENERIC_KEY_V2 else 0,
            "t": "pack",
            "uid": 0,
            "tcid": device_tcid,
            "pack": pack,
            "tag": tag,
        }
    else:
        envelope = {
            "cid": "app",
            "i": 1 if key == GENERIC_KEY else 0,
            "t": "pack",
            "uid": 0,
            "tcid": device_tcid,
            "pack": encrypt(inner, key),
        }
    return json.dumps(envelope, separators=(",", ":")).encode("utf-8")


class _RequestProtocol(asyncio.DatagramProtocol):
    """Datagram protocol that completes a future on the first reply."""

    def __init__(self) -> None:
        self.future: asyncio.Future[tuple[bytes, tuple[str, int]]] = (
            asyncio.get_event_loop().create_future()
        )

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if not self.future.done():
            self.future.set_result((data, addr))


class _SessionProtocol(asyncio.DatagramProtocol):
    """Collects multiple replies on one socket (scan then bind)."""

    def __init__(self) -> None:
        self.replies: list[tuple[bytes, tuple[str, int]]] = []

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.replies.append((data, addr))


class _BroadcastProtocol(asyncio.DatagramProtocol):
    """Datagram protocol that collects every reply for a fixed window."""

    def __init__(self) -> None:
        self.replies: list[tuple[bytes, tuple[str, int]]] = []

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.replies.append((data, addr))

    def error_received(self, exc: Exception) -> None:
        _LOGGER.debug("UDP broadcast error: %s", exc)


async def send_request(
    host: str,
    port: int,
    key: bytes,
    payload: dict[str, Any],
    timeout: float = DEFAULT_TIMEOUT,
    version: int = PROTO_V1,
) -> dict[str, Any]:
    """Send an encrypted request and return the decrypted reply.

    The reply ``pack`` field is decrypted with the same ``key`` and
    ``version`` used to encrypt the request. Mismatches raise
    :class:`EwpeAuthError`.
    """
    inner, _v = await _send_raw(
        host,
        port,
        _outer_packet(
            payload,
            key,
            version,
            tcid=str(payload.get("mac", "")),
        ),
        reply_key=key,
        reply_version=version,
        timeout=timeout,
    )
    return inner


async def unicast_scan(
    host: str, port: int, timeout: float = DEFAULT_TIMEOUT
) -> tuple[dict[str, Any], int]:
    """Send a raw scan to one host and return ``(dev_reply, version)``.

    Both V1 and V2 devices accept the raw ``{"t":"scan"}`` JSON. The reply
    envelope tells us which protocol the device speaks: a ``tag`` field next
    to ``pack`` flags V2 (AES-GCM), otherwise V1 (AES-ECB). The matching
    generic key is used to decrypt ``pack``.
    """
    raw = json.dumps({"t": "scan"}, separators=(",", ":")).encode("utf-8")
    _LOGGER.debug("Sending raw unicast scan to %s:%s", host, port)
    return await _send_raw(
        host, port, raw, reply_key=None, reply_version=None, timeout=timeout
    )


async def _send_raw(
    host: str,
    port: int,
    packet: bytes,
    reply_key: bytes | None,
    reply_version: int | None,
    timeout: float,
) -> tuple[dict[str, Any], int]:
    """Open an ephemeral socket, send ``packet`` once, parse the first reply."""
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        _RequestProtocol, remote_addr=(host, port)
    )
    try:
        transport.sendto(packet)
        try:
            data, _addr = await asyncio.wait_for(protocol.future, timeout=timeout)
        except TimeoutError as err:
            raise EwpeTimeout(f"No reply from {host}:{port} in {timeout}s") from err
    finally:
        transport.close()
    return _parse_reply(data, reply_key, reply_version)


async def _session_exchange(
    host: str,
    port: int,
    packets: list[bytes],
    timeout: float,
) -> list[bytes]:
    """Send ``packets`` in order on one socket and wait for one reply each."""
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        _SessionProtocol, remote_addr=(host, port)
    )
    replies: list[bytes] = []
    try:
        for packet in packets:
            before = len(protocol.replies)
            transport.sendto(packet)
            deadline = loop.time() + timeout
            while len(protocol.replies) <= before:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise EwpeTimeout(
                        f"No reply from {host}:{port} in {timeout}s"
                    )
                await asyncio.sleep(min(0.05, remaining))
            replies.append(protocol.replies[before][0])
    finally:
        transport.close()
    return replies


async def scan_then_bind(
    host: str,
    port: int,
    timeout: float = DEFAULT_TIMEOUT,
    bind_timeout: float = DEFAULT_BIND_TIMEOUT,
    version: int | None = None,
) -> tuple[dict[str, Any], int, dict[str, Any]]:
    """Unicast scan and bind on one socket.

    Many Gree units (including some that reply to scan with a V1-style
    envelope) only accept the bind handshake over V2 (AES-GCM). When the
    first bind attempt times out we fall back to the other protocol, matching
    ``greeclimate`` behaviour.
    """
    scan_packet = json.dumps({"t": "scan"}).encode("utf-8")
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        _SessionProtocol, remote_addr=(host, port)
    )

    async def _await_reply(before: int, wait: float) -> bytes:
        deadline = loop.time() + wait
        while len(protocol.replies) <= before:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise EwpeTimeout(f"No reply from {host}:{port} in {wait}s")
            await asyncio.sleep(min(0.05, remaining))
        return protocol.replies[before][0]

    try:
        transport.sendto(scan_packet)
        scan_data = await _await_reply(0, timeout)
        dev_reply, detected = _parse_reply(scan_data)
        if dev_reply.get("t") != "dev":
            raise EwpeProtocolError(f"Unexpected scan reply: {dev_reply!r}")
        mac = dev_reply.get("cid") or dev_reply.get("mac")
        if not mac:
            raise EwpeProtocolError("Scan reply contains no MAC")

        if version is None:
            versions_to_try = (
                [PROTO_V2, PROTO_V1] if detected == PROTO_V2 else [PROTO_V1, PROTO_V2]
            )
        elif version == PROTO_V2:
            versions_to_try = [PROTO_V2, PROTO_V1]
        else:
            versions_to_try = [PROTO_V1, PROTO_V2]

        last_timeout: EwpeTimeout | None = None
        for try_version in versions_to_try:
            bind_key = GENERIC_KEY_V2 if try_version == PROTO_V2 else GENERIC_KEY
            bind_packet = _outer_packet(
                {"t": "bind", "mac": mac, "uid": 0},
                bind_key,
                try_version,
                tcid=str(mac),
            )
            before = len(protocol.replies)
            transport.sendto(bind_packet)
            try:
                bind_data = await _await_reply(before, bind_timeout)
            except EwpeTimeout as err:
                _LOGGER.debug(
                    "Bind attempt on %s:%s using proto v%d timed out",
                    host,
                    port,
                    try_version,
                )
                last_timeout = err
                continue
            bind_reply, _ = _parse_reply(bind_data, bind_key, try_version)
            if bind_reply.get("t") == "bindok":
                return dev_reply, try_version, bind_reply
            raise EwpeProtocolError(f"Unexpected bind reply: {bind_reply!r}")

        if last_timeout is not None:
            raise last_timeout
        raise EwpeTimeout(f"No reply from {host}:{port} in {bind_timeout}s")
    finally:
        transport.close()


def _parse_reply(
    data: bytes,
    key: bytes | None = None,
    version: int | None = None,
) -> tuple[dict[str, Any], int]:
    """Parse and decrypt a reply envelope.

    If ``key`` and ``version`` are both ``None`` (the scan path), the version
    is auto-detected from the envelope and the matching generic key is used.
    Otherwise the caller commits to a specific version/key (used for status
    and cmd against an already-bound device).
    """
    try:
        envelope = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise EwpeProtocolError("Reply is not valid JSON") from err
    if "pack" not in envelope:
        raise EwpeProtocolError(f"Reply has no 'pack' field: {envelope!r}")

    detected = PROTO_V2 if "tag" in envelope else PROTO_V1
    use_version = version if version is not None else detected
    if key is not None:
        use_key = key
    else:
        use_key = GENERIC_KEY_V2 if use_version == PROTO_V2 else GENERIC_KEY

    if use_version == PROTO_V2:
        if "tag" not in envelope:
            raise EwpeProtocolError("V2 reply missing 'tag' field")
        return decrypt_v2(envelope["pack"], envelope["tag"], use_key), PROTO_V2
    return decrypt(envelope["pack"], use_key), PROTO_V1


async def scan(
    broadcast_addr: str,
    port: int,
    timeout: float,
) -> list[dict[str, Any]]:
    """Broadcast a scan packet and return decrypted ``dev`` replies.

    Each returned dict carries a ``_version`` key (PROTO_V1 or PROTO_V2) so
    the config flow knows how to bind to the chosen device.
    """
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setblocking(False)
    sock.bind(("", 0))

    transport, protocol = await loop.create_datagram_endpoint(
        _BroadcastProtocol, sock=sock
    )
    try:
        scan_packet = json.dumps({"t": "scan"}).encode("utf-8")
        transport.sendto(scan_packet, (broadcast_addr, port))
        await asyncio.sleep(timeout)
    finally:
        transport.close()

    devices: list[dict[str, Any]] = []
    for data, (addr, _port) in protocol.replies:
        try:
            inner, version = _parse_reply(data)
        except EwpeError as err:
            _LOGGER.debug("Ignoring scan reply from %s: %s", addr, err)
            continue
        inner.setdefault("address", addr)
        inner["_version"] = version
        devices.append(inner)
    return devices
