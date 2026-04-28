"""Low-level EWPE Smart / Gree wire protocol.

This module deliberately avoids any ``homeassistant`` imports so that it can be
exercised by a plain pytest run without spinning up Home Assistant.

Wire format reference:
- https://github.com/tomikaa87/gree-remote
- https://github.com/stas-demydiuk/ewpe-smart-mqtt
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import socket
from typing import Any

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .const import DEFAULT_TIMEOUT, GENERIC_KEY

_LOGGER = logging.getLogger(__name__)

_BLOCK_BITS = 128  # AES block size in bits, used by PKCS#7 padder
_BLOCK_BYTES = _BLOCK_BITS // 8


class EwpeError(Exception):
    """Base exception for EWPE Smart protocol failures."""


class EwpeTimeout(EwpeError):
    """Raised when the device does not reply within the timeout."""


class EwpeProtocolError(EwpeError):
    """Raised when the reply has the wrong type or cannot be parsed."""


class EwpeAuthError(EwpeError):
    """Raised when a reply cannot be decrypted with the supplied key."""


def _aes_ecb(key: bytes) -> Cipher:
    # ECB is mandated by the device protocol — the wire format predates
    # modern cipher modes. We can't pick something safer here.
    return Cipher(algorithms.AES(key), modes.ECB())  # nosec B305


def encrypt(payload: dict[str, Any], key: bytes = GENERIC_KEY) -> str:
    """AES-128 ECB encrypt ``payload`` and return base64 ASCII."""
    plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    padder = padding.PKCS7(_BLOCK_BITS).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = _aes_ecb(key).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ciphertext).decode("ascii")


def decrypt(ciphertext: str, key: bytes = GENERIC_KEY) -> dict[str, Any]:
    """Decrypt a base64 AES-128 ECB blob into a JSON object."""
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
        return json.loads(decoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise EwpeAuthError("Decrypted payload is not valid JSON") from err


def _outer_packet(inner: dict[str, Any], key: bytes) -> bytes:
    """Wrap an inner payload in the outer envelope and serialise to bytes."""
    envelope = {
        "cid": "app",
        "i": 1 if key == GENERIC_KEY else 0,
        "t": "pack",
        "uid": 0,
        "tcid": "",
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

    def error_received(self, exc: Exception) -> None:
        if not self.future.done():
            self.future.set_exception(exc)

    def connection_lost(self, exc: Exception | None) -> None:
        if not self.future.done() and exc is not None:
            self.future.set_exception(exc)


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
) -> dict[str, Any]:
    """Send an encrypted request to ``host:port`` and return the decrypted reply.

    The reply ``pack`` field is decrypted with the same ``key`` that was used to
    encrypt the request. Mismatched keys raise :class:`EwpeAuthError`.
    """
    return await _send_raw(
        host, port, _outer_packet(payload, key), reply_key=key, timeout=timeout
    )


async def unicast_scan(
    host: str, port: int, timeout: float = DEFAULT_TIMEOUT
) -> dict[str, Any]:
    """Send a raw (unencrypted) scan packet to one host and return the dev reply.

    The reference EWPE Smart wire format treats the scan packet specially —
    devices reply only when the scan is sent as raw JSON (no outer envelope,
    no encryption). The reply itself is wrapped in the standard envelope with
    its ``pack`` field encrypted using the generic key.
    """
    raw = json.dumps({"t": "scan"}, separators=(",", ":")).encode("utf-8")
    _LOGGER.debug("Sending raw unicast scan to %s:%s", host, port)
    return await _send_raw(host, port, raw, reply_key=GENERIC_KEY, timeout=timeout)


async def _send_raw(
    host: str,
    port: int,
    packet: bytes,
    reply_key: bytes,
    timeout: float,
) -> dict[str, Any]:
    """Open an ephemeral socket, send ``packet`` once, decrypt the first reply."""
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
    return _parse_reply(data, reply_key)


def _parse_reply(data: bytes, key: bytes) -> dict[str, Any]:
    try:
        envelope = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise EwpeProtocolError("Reply is not valid JSON") from err
    if "pack" not in envelope:
        raise EwpeProtocolError(f"Reply has no 'pack' field: {envelope!r}")
    return decrypt(envelope["pack"], key)


async def scan(
    broadcast_addr: str,
    port: int,
    timeout: float,
) -> list[dict[str, Any]]:
    """Broadcast a scan packet and return decrypted ``dev`` replies."""
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
            inner = _parse_reply(data, GENERIC_KEY)
        except EwpeError as err:
            _LOGGER.debug("Ignoring scan reply from %s: %s", addr, err)
            continue
        inner.setdefault("address", addr)
        devices.append(inner)
    return devices
