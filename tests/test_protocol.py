"""Unit tests for the AES wire-format helpers."""

from __future__ import annotations

import pytest

from custom_components.ewpe_smart.const import GENERIC_KEY_V2
from custom_components.ewpe_smart.const import PARAM_BUZZER_ON_OFF
from custom_components.ewpe_smart.protocol import (
    EwpeAuthError,
    EwpeProtocolError,
    append_silent_buzzer,
    decrypt,
    decrypt_v2,
    encrypt,
    encrypt_v2,
    parse_cmd_reply,
)


def test_parse_cmd_reply_accepts_val_or_p() -> None:
    with_val = {
        "t": "res",
        "mac": "580d0df2deaf",
        "opt": ["Lig"],
        "val": [0],
        "r": 200,
    }
    assert parse_cmd_reply(with_val) == {"Lig": 0}

    with_p = {
        "t": "res",
        "mac": "580d0df2deaf",
        "opt": ["Lig", "Buzzer_ON_OFF"],
        "p": [0, 1],
        "r": 200,
    }
    assert parse_cmd_reply(with_p) == {"Lig": 0, "Buzzer_ON_OFF": 1}


def test_parse_cmd_reply_rejects_missing_values() -> None:
    with pytest.raises(EwpeProtocolError):
        parse_cmd_reply({"t": "res", "mac": "aa", "opt": ["Pow"]})


def test_append_silent_buzzer_adds_param_once() -> None:
    opt = ["Pow"]
    p = [1]
    append_silent_buzzer(opt, p)
    assert opt == ["Pow", PARAM_BUZZER_ON_OFF]
    assert p == [1, 1]
    append_silent_buzzer(opt, p)
    assert opt.count(PARAM_BUZZER_ON_OFF) == 1


def test_encrypt_decrypt_roundtrip_default_key() -> None:
    payload = {"t": "scan"}
    cipher = encrypt(payload)
    assert decrypt(cipher) == payload


def test_encrypt_decrypt_roundtrip_device_key() -> None:
    key = b"abcdefghijklmnop"
    payload = {
        "cols": ["Pow", "Mod", "SetTem"],
        "mac": "AA:BB:CC:DD:EE:FF",
        "t": "status",
    }
    cipher = encrypt(payload, key)
    assert decrypt(cipher, key) == payload


def test_decrypt_with_wrong_key_raises_auth_error() -> None:
    payload = {"t": "bind", "uid": 0}
    cipher = encrypt(payload, b"abcdefghijklmnop")
    with pytest.raises(EwpeAuthError):
        decrypt(cipher, b"ponmlkjihgfedcba")


def test_encrypt_produces_ascii_base64() -> None:
    payload = {"t": "scan"}
    cipher = encrypt(payload)
    cipher.encode("ascii")  # would raise UnicodeEncodeError on non-ASCII
    assert len(cipher) % 4 == 0


def test_v1_bind_ciphertext_matches_greeclimate() -> None:
    """Wire bytes must match greeclimate so Gree firmware accepts bind."""
    payload = {"t": "bind", "mac": "580d0df2deaf", "uid": 0}
    assert encrypt(payload) == (
        "UH1xnvFY7toQqZpWdQqnj8Y01Y3RTO6WGC8Szx4uAGxYKP+bEKm/j2Ku1yi1i584"
    )


# ── V2 (AES-GCM) ──────────────────────────────────────────────────────────


def test_v2_encrypt_decrypt_roundtrip_default_key() -> None:
    payload = {"t": "scan"}
    pack, tag = encrypt_v2(payload)
    assert decrypt_v2(pack, tag) == payload


def test_v2_encrypt_decrypt_roundtrip_device_key() -> None:
    key = b"abcdefghijklmnop"
    payload = {"mac": "AA:BB:CC:DD:EE:FF", "t": "bind", "uid": 0}
    pack, tag = encrypt_v2(payload, key)
    assert decrypt_v2(pack, tag, key) == payload


def test_v2_decrypt_with_wrong_key_raises_auth_error() -> None:
    pack, tag = encrypt_v2({"t": "scan"}, GENERIC_KEY_V2)
    with pytest.raises(EwpeAuthError):
        decrypt_v2(pack, tag, b"0123456789abcdef")


def test_v2_decrypt_with_tampered_tag_raises_auth_error() -> None:
    pack, _tag = encrypt_v2({"t": "scan"})
    with pytest.raises(EwpeAuthError):
        decrypt_v2(pack, "AAAAAAAAAAAAAAAAAAAAAA==")


def test_v2_encrypt_produces_two_separate_b64_strings() -> None:
    pack, tag = encrypt_v2({"t": "scan"})
    pack.encode("ascii")
    tag.encode("ascii")
    # GCM tag is always 16 bytes → 24 chars base64 (with padding)
    assert len(tag) == 24
