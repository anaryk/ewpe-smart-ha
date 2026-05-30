#!/usr/bin/env python3
"""Standalone probe for an EWPE Smart / Gree device.

Subcommands:

    scan   — discover protocol version (default when IP given directly)
    status — read full device state (requires device key from bind)
    set    — write one or more parameters

Run this on the same host that runs Home Assistant — only that machine's
view of the network matters for the integration.

Usage:
    python3 tools/probe.py 192.168.1.50 --decrypt
    python3 tools/probe.py scan 192.168.1.50 --decrypt --bind
    python3 tools/probe.py status 192.168.1.50 --key DEVICEKEY --mac AA:BB:...
    python3 tools/probe.py set 192.168.1.50 --key DEVICEKEY --mac AA:BB:... Quiet=1
    python3 tools/probe.py set 192.168.1.50 --key DEVICEKEY --mac AA:BB:... --silent Quiet=1
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

# Keep in sync with custom_components/ewpe_smart/const.py
PARAM_BUZZER_ON_OFF = "Buzzer_ON_OFF"
BUZZER_SILENT = 1

# Keep in sync with custom_components/ewpe_smart/const.py STATUS_PARAMS
STATUS_PARAMS = [
    "Pow",
    "Mod",
    "SetTem",
    "TemUn",
    "WdSpd",
    "TemSen",
    "SwhSlp",
    "Tur",
    "Quiet",
    "Blo",
    "Health",
    "Lig",
    "SvSt",
    "Air",
]


def _encrypt_v1(payload: dict, key: bytes = V1_KEY) -> str:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    plaintext = json.dumps(payload).encode("utf-8")
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.ECB())  # nosec B305
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ciphertext).decode("ascii")


def _encrypt_v2(payload: dict, key: bytes = V2_KEY) -> tuple[str, str]:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    plaintext = json.dumps(payload).encode("utf-8")
    aesgcm = AESGCM(key)
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


def _outer_packet(
    inner: dict,
    version: int,
    key: bytes,
    *,
    tcid: str = "",
    bind: bool = False,
) -> bytes:
    device_tcid = tcid or str(inner.get("mac", ""))
    if bind:
        i_field = 1
    elif version == 2:
        i_field = 1 if key == V2_KEY else 0
    else:
        i_field = 1 if key == V1_KEY else 0

    if version == 2:
        pack, tag = _encrypt_v2(inner, key)
        envelope = {
            "cid": "app",
            "i": i_field,
            "t": "pack",
            "uid": 0,
            "tcid": device_tcid,
            "pack": pack,
            "tag": tag,
        }
    else:
        envelope = {
            "cid": "app",
            "i": i_field,
            "t": "pack",
            "uid": 0,
            "tcid": device_tcid,
            "pack": _encrypt_v1(inner, key),
        }
    return json.dumps(envelope, separators=(",", ":")).encode("utf-8")


def _parse_envelope(envelope: dict, key: bytes) -> dict:
    if "tag" in envelope:
        return _decrypt_v2(envelope["pack"], envelope["tag"], key)
    return _decrypt_v1(envelope["pack"], key)


def _send_request(
    ip: str,
    key: bytes,
    inner: dict,
    version: int,
    *,
    mac: str,
    timeout: float = TIMEOUT,
) -> dict:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    sock.bind(("", 0))
    try:
        packet = _outer_packet(inner, version, key, tcid=mac)
        sock.sendto(packet, (ip, PORT))
        data, addr = sock.recvfrom(4096)
        envelope = json.loads(data.decode("utf-8"))
        try:
            reply = _parse_envelope(envelope, key)
        except Exception as err:
            raise ValueError(f"decrypt failed: {err}") from err
        print(f"[{ip}] ← reply from {addr[0]}:{addr[1]} (proto v{version})")
        return reply
    finally:
        sock.close()


def _send_request_auto(
    ip: str,
    key: bytes,
    inner: dict,
    *,
    mac: str,
    version: int | None = None,
) -> dict:
    """Send a device-key request, trying v1 then v2 when version is omitted."""
    versions = (version,) if version is not None else (1, 2)
    for idx, try_version in enumerate(versions):
        if version is None and len(versions) > 1:
            print(f"[{ip}] → trying proto v{try_version}...")
        try:
            return _send_request(ip, key, inner, try_version, mac=mac)
        except TimeoutError:
            if version is not None or idx == len(versions) - 1:
                raise
            print(f"[{ip}]   ✗ v{try_version}: no reply within {TIMEOUT}s")
        except (OSError, json.JSONDecodeError, ValueError) as err:
            if version is not None or idx == len(versions) - 1:
                raise
            print(f"[{ip}]   ✗ v{try_version}: {err}")
    raise TimeoutError(f"no reply from {ip} on any protocol version")


def bind(ip: str, mac: str, sock: socket.socket | None = None) -> int:
    own_sock = sock is None
    if own_sock:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(BIND_TIMEOUT)
        sock.bind(("", 0))
    versions = (1, 2)
    try:
        for version in versions:
            key = V2_KEY if version == 2 else V1_KEY
            packet = _outer_packet(
                {"t": "bind", "mac": mac, "uid": 0},
                version,
                key,
                tcid=mac,
                bind=True,
            )
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
            reply_key = V2_KEY if "tag" in envelope else V1_KEY
            inner = _parse_envelope(envelope, reply_key)
            print(f"[{ip}] ← bind reply from {addr[0]}:{addr[1]} (proto v{version})")
            print(f"[{ip}]   inner: {inner}")
            if inner.get("t") == "bindok" and inner.get("key"):
                device_key = inner["key"]
                print(f"[{ip}]   ✓ bind OK (device key received, proto v{version})")
                print(f"[{ip}]   key: {device_key}")
                print(
                    f"[{ip}]   next: python3 tools/probe.py status {ip} "
                    f"--key '{device_key}' --mac '{mac}'"
                )
                if version == 2:
                    print(
                        f"[{ip}]   note: hybrid firmware — encrypted traffic uses proto v2 "
                        "(auto-detected if --version omitted)"
                    )
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
                generic_key = V2_KEY if version == 2 else V1_KEY
                info = _parse_envelope(envelope, generic_key)
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


def cmd_status(ip: str, key: str, mac: str, version: int | None) -> int:
    device_key = key.encode("utf-8")
    version_label = f"v{version}" if version else "auto"
    print(f"[{ip}] → status request ({len(STATUS_PARAMS)} cols, proto {version_label})")
    try:
        reply = _send_request_auto(
            ip,
            device_key,
            {"t": "status", "mac": mac, "cols": STATUS_PARAMS},
            mac=mac,
            version=version,
        )
    except TimeoutError:
        print(f"[{ip}]   ✗ no reply within {TIMEOUT}s on any protocol version")
        return 1
    except (OSError, json.JSONDecodeError, ValueError) as err:
        print(f"[{ip}]   ✗ status failed: {err}")
        return 2

    if reply.get("t") != "dat":
        print(f"[{ip}]   ✗ unexpected reply: {reply}")
        return 3

    cols = reply.get("cols") or []
    dat = reply.get("dat") or []
    print(f"[{ip}]   cols ({len(cols)}): {cols}")
    for name, value in zip(cols, dat, strict=False):
        print(f"[{ip}]     {name} = {value}")
    switch_cols = [c for c in cols if c in STATUS_PARAMS[6:]]
    if switch_cols:
        print(f"[{ip}]   supported switches: {', '.join(switch_cols)}")
    else:
        print(f"[{ip}]   supported switches: (none in reply)")
    return 0


def _append_silent_buzzer(opt: list[str], p: list[int]) -> None:
    """Keep in sync with custom_components/ewpe_smart/protocol.py."""
    if PARAM_BUZZER_ON_OFF not in opt:
        opt.append(PARAM_BUZZER_ON_OFF)
        p.append(BUZZER_SILENT)


def _parse_params(values: list[str]) -> dict[str, int]:
    params: dict[str, int] = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"expected Param=value, got {item!r}")
        name, raw = item.split("=", 1)
        params[name] = int(raw)
    return params


def cmd_set(
    ip: str,
    key: str,
    mac: str,
    version: int | None,
    params: dict[str, int],
    *,
    silent: bool = False,
) -> int:
    device_key = key.encode("utf-8")
    opt = list(params.keys())
    values = list(params.values())
    if silent:
        _append_silent_buzzer(opt, values)
    version_label = f"v{version}" if version else "auto"
    print(f"[{ip}] → set {dict(zip(opt, values, strict=True))} (proto {version_label})")
    try:
        reply = _send_request_auto(
            ip,
            device_key,
            {"t": "cmd", "mac": mac, "opt": opt, "p": values},
            mac=mac,
            version=version,
        )
    except TimeoutError:
        print(f"[{ip}]   ✗ no reply within {TIMEOUT}s on any protocol version")
        return 1
    except (OSError, json.JSONDecodeError, ValueError) as err:
        print(f"[{ip}]   ✗ set failed: {err}")
        return 2

    if reply.get("t") != "res":
        print(f"[{ip}]   ✗ unexpected reply: {reply}")
        return 3

    values = reply.get("val")
    if not isinstance(values, list):
        values = reply.get("p")
    for name, value in zip(reply.get("opt") or [], values or [], strict=False):
        print(f"[{ip}]     {name} = {value}")
    return 0


def _add_device_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("ip", help="Device IP address")
    parser.add_argument("--key", required=True, help="Device key from bind / HA config")
    parser.add_argument("--mac", required=True, help="Device MAC address")
    parser.add_argument(
        "--version",
        type=int,
        choices=(1, 2),
        default=None,
        help="Protocol version for encrypted traffic (default: auto — try v1 then v2)",
    )


def main(argv: list[str]) -> int:
    # Legacy usage: probe.py <ip> [--decrypt] [--bind]
    if argv and argv[0] not in {"scan", "status", "set"} and not argv[0].startswith("-"):
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

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Scan / discover a device")
    scan_parser.add_argument("ips", nargs="+", help="Device IP addresses")
    scan_parser.add_argument(
        "--decrypt",
        action="store_true",
        help="Also decrypt the dev info using the matching generic key.",
    )
    scan_parser.add_argument(
        "--bind",
        action="store_true",
        help="After scan, run the encrypted bind handshake (implies --decrypt).",
    )

    status_parser = subparsers.add_parser("status", help="Read device status")
    _add_device_args(status_parser)

    set_parser = subparsers.add_parser("set", help="Set device parameters")
    _add_device_args(set_parser)
    set_parser.add_argument(
        "--silent",
        action="store_true",
        help="Suppress the confirmation beep on this command",
    )
    set_parser.add_argument(
        "params",
        nargs="+",
        metavar="Param=value",
        help="Parameter assignments, e.g. Quiet=1 Lig=0",
    )

    args = parser.parse_args(argv)

    if args.command == "scan":
        decrypt = args.decrypt or args.bind
        rc = 0
        for ip in args.ips:
            rc = max(rc, probe(ip, decrypt, args.bind))
            print()
        return rc

    if args.command == "status":
        return cmd_status(args.ip, args.key, args.mac, args.version)

    try:
        params = _parse_params(args.params)
    except ValueError as err:
        print(f"error: {err}")
        return 2
    return cmd_set(
        args.ip, args.key, args.mac, args.version, params, silent=args.silent
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
