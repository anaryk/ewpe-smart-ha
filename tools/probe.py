#!/usr/bin/env python3
"""Standalone probe for an EWPE Smart / Gree device.

Sends a raw scan packet to ``<ip>:7000`` and prints what comes back. Tells
you whether the device speaks the original V1 protocol (AES-ECB) or the
newer V2 protocol (AES-GCM, used by commercial U-Match controllers like the
XE7A series), or whether it's unreachable from this host.

Run this on the same host that runs Home Assistant — only that machine's
view of the network matters for the integration.

Usage:
    python3 tools/probe.py <device-ip> [<device-ip> ...]

Optional ``--decrypt`` flag tries the matching generic key on the encrypted
``pack`` field and prints the dev info (brand/model/MAC/name).

Optional ``--bind`` runs the encrypted bind handshake after a successful scan
(same step Home Assistant runs when you pick a discovered device).
"""

from __future__ import annotations

import argparse
import base64
import json
import socket
import sys

PORT = 7000
TIMEOUT = 5.0
BIND_TIMEOUT = 10.0

# V1 generic key — AES-128 ECB
V1_KEY = b"a3K8Bx%2r8Y7#xDh"
# V2 generic key + GCM nonce + AAD — AES-128 GCM
V2_KEY = b"{yxAHAY_Lm6pbC/<"
V2_NONCE = b"\x54\x40\x78\x44\x49\x67\x5a\x51\x6c\x5e\x63\x13"
V2_AAD = b"qualcomm-test"


def _encrypt_v1(payload: dict) -> str:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    plaintext = json.dumps(payload).encode("utf-8")
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(V1_KEY), modes.ECB())  # nosec B305
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ciphertext).decode("ascii")


def _encrypt_v2(payload: dict) -> tuple[str, str]:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    plaintext = json.dumps(payload).encode("utf-8")
    aesgcm = AESGCM(V2_KEY)
    ct_with_tag = aesgcm.encrypt(V2_NONCE, plaintext, V2_AAD)
    ciphertext, tag = ct_with_tag[:-16], ct_with_tag[-16:]
    return (
        base64.b64encode(ciphertext).decode("ascii"),
        base64.b64encode(tag).decode("ascii"),
    )


def _decrypt_v1(pack_b64: str, key: bytes = V1_KEY) -> dict:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    raw = base64.b64decode(pack_b64)
    cipher = Cipher(algorithms.AES(key), modes.ECB())  # nosec B305
    decryptor = cipher.decryptor()
    padded = decryptor.update(raw) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    plain = unpadder.update(padded) + unpadder.finalize()
    return json.loads(plain.decode("utf-8"))


def _decrypt_v2(pack_b64: str, tag_b64: str, key: bytes = V2_KEY) -> dict:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    ciphertext = base64.b64decode(pack_b64)
    tag = base64.b64decode(tag_b64)
    aesgcm = AESGCM(key)
    plain = aesgcm.decrypt(V2_NONCE, ciphertext + tag, V2_AAD)
    text = plain.decode("utf-8", errors="replace")
    last = text.rfind("}")
    if last >= 0:
        text = text[: last + 1]
    return json.loads(text)


def _outer_packet(inner: dict, version: int, tcid: str = "") -> bytes:
    if version == 2:
        pack, tag = _encrypt_v2(inner)
        envelope = {
            "cid": "app",
            "i": 1,
            "t": "pack",
            "uid": 0,
            "tcid": tcid,
            "pack": pack,
            "tag": tag,
        }
    else:
        envelope = {
            "cid": "app",
            "i": 1,
            "t": "pack",
            "uid": 0,
            "tcid": tcid,
            "pack": _encrypt_v1(inner),
        }
    return json.dumps(envelope, separators=(",", ":")).encode("utf-8")


def _parse_envelope(envelope: dict, version: int) -> dict:
    if version == 2:
        if "tag" not in envelope:
            raise ValueError("V2 reply missing tag")
        return _decrypt_v2(envelope["pack"], envelope["tag"])
    return _decrypt_v1(envelope["pack"])


def bind(ip: str, mac: str, sock: socket.socket | None = None) -> int:
    own_sock = sock is None
    if own_sock:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(BIND_TIMEOUT)
        sock.bind(("", 0))
    versions = (1, 2)
    try:
        for version in versions:
            packet = _outer_packet({"t": "bind", "mac": mac, "uid": 0}, version, tcid=mac)
            print(
                f"[{ip}] → sending encrypted bind v{version} "
                f"({len(packet)} B) to {ip}:{PORT}"
            )
            sock.settimeout(BIND_TIMEOUT)
            sock.sendto(packet, (ip, PORT))
            try:
                data, addr = sock.recvfrom(4096)
            except TimeoutError:
                print(f"[{ip}]   ✗ bind v{version}: no reply within {BIND_TIMEOUT}s")
                continue
            envelope = json.loads(data.decode("utf-8"))
            reply_version = 2 if "tag" in envelope else 1
            inner = _parse_envelope(envelope, reply_version)
            print(f"[{ip}] ← bind reply from {addr[0]}:{addr[1]} (proto v{reply_version})")
            print(f"[{ip}]   inner: {inner}")
            if inner.get("t") == "bindok" and inner.get("key"):
                print(f"[{ip}]   ✓ bind OK (device key received)")
                return 0
            print(f"[{ip}]   ✗ unexpected bind reply")
            return 6
        return 1
    except (OSError, json.JSONDecodeError, ValueError) as err:
        print(f"[{ip}]   ✗ bind failed: {err}")
        return 6
    finally:
        if own_sock:
            sock.close()


def probe(ip: str, decrypt: bool, do_bind: bool) -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT)
    sock.bind(("", 0))
    try:
        packet = json.dumps({"t": "scan"}).encode()
        print(f"[{ip}] → sending raw scan ({len(packet)} B) to {ip}:{PORT}")
        try:
            sock.sendto(packet, (ip, PORT))
        except OSError as err:
            print(f"[{ip}]   sendto failed: {err}")
            return 2
        try:
            data, addr = sock.recvfrom(4096)
        except TimeoutError:
            print(f"[{ip}]   ✗ no reply within {TIMEOUT}s")
            print(
                f"[{ip}]     → device unreachable from this host. "
                "Check VLAN/firewall, or Docker bridge networking on HA."
            )
            return 1

        print(f"[{ip}] ← reply from {addr[0]}:{addr[1]} ({len(data)} B)")
        try:
            envelope = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as err:
            print(f"[{ip}]   ✗ reply is not JSON: {err}")
            print(f"[{ip}]     raw: {data!r}")
            return 3

        keys = sorted(envelope.keys())
        print(f"[{ip}]   envelope keys: {keys}")
        version = 2 if "tag" in envelope else 1
        if version == 2:
            print(
                f"[{ip}]   → V2 protocol detected (AES-GCM). "
                "Integration ≥ 0.1.2 supports this."
            )
        elif "pack" in envelope:
            print(f"[{ip}]   → V1 protocol detected (AES-ECB).")
        else:
            print(f"[{ip}]   ?? unknown envelope: {envelope}")
            return 5

        info: dict | None = None
        if decrypt and "pack" in envelope:
            try:
                info = _parse_envelope(envelope, version)
            except Exception as err:
                print(f"[{ip}]   ✗ decrypt failed: {err}")
                return 4
            print(f"[{ip}]   info: {info}")

        if do_bind:
            if not info:
                print(f"[{ip}]   ✗ --bind requires --decrypt to obtain MAC")
                return 4
            mac = info.get("cid") or info.get("mac")
            if not mac:
                print(f"[{ip}]   ✗ scan reply has no MAC/cid")
                return 4
            return bind(ip, mac, sock=sock)
        return 0
    finally:
        sock.close()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ips", nargs="+", help="Device IP addresses")
    parser.add_argument(
        "--decrypt",
        action="store_true",
        help="Also decrypt the dev info using the matching generic key.",
    )
    parser.add_argument(
        "--bind",
        action="store_true",
        help="After scan, run the encrypted bind handshake (implies --decrypt).",
    )
    args = parser.parse_args(argv)
    decrypt = args.decrypt or args.bind
    rc = 0
    for ip in args.ips:
        rc = max(rc, probe(ip, decrypt, args.bind))
        print()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
