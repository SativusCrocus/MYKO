"""KeyManager: roundtrip, wrong-passphrase failure, per-call salt uniqueness."""

from __future__ import annotations

import pytest

from backend.crypto import NONCE_LEN, SALT_LEN, TAG_LEN, CryptoError, KeyManager


def test_roundtrip_preserves_plaintext():
    km = KeyManager("correct-horse-battery-staple")
    plaintext = b"the quick brown fox jumps over the lazy dog"
    blob = km.encrypt(plaintext)
    assert km.decrypt(blob) == plaintext


def test_blob_layout_has_expected_prefix_lengths():
    km = KeyManager("correct-horse-battery-staple")
    blob = km.encrypt(b"x")
    # salt + nonce + (ciphertext of 1 byte) + tag
    assert len(blob) == SALT_LEN + NONCE_LEN + 1 + TAG_LEN


def test_wrong_passphrase_rejects_ciphertext():
    km_a = KeyManager("passphrase-a-long-enough")
    km_b = KeyManager("different-passphrase-b")
    blob = km_a.encrypt(b"secret")
    with pytest.raises(CryptoError):
        km_b.decrypt(blob)


def test_each_encrypt_uses_unique_salt_and_nonce():
    km = KeyManager("stable-passphrase-1234")
    blob_a = km.encrypt(b"same plaintext")
    blob_b = km.encrypt(b"same plaintext")
    assert blob_a != blob_b
    assert blob_a[:SALT_LEN] != blob_b[:SALT_LEN]
    assert blob_a[SALT_LEN : SALT_LEN + NONCE_LEN] != blob_b[SALT_LEN : SALT_LEN + NONCE_LEN]


def test_tampered_ciphertext_fails():
    km = KeyManager("stable-passphrase-1234")
    blob = bytearray(km.encrypt(b"data"))
    # Flip a bit in the ciphertext region
    blob[SALT_LEN + NONCE_LEN] ^= 0x01
    with pytest.raises(CryptoError):
        km.decrypt(bytes(blob))


def test_empty_passphrase_rejected():
    with pytest.raises(CryptoError):
        KeyManager("")


def test_short_blob_rejected():
    km = KeyManager("stable-passphrase-1234")
    with pytest.raises(CryptoError):
        km.decrypt(b"\x00" * 10)


def test_empty_plaintext_roundtrip():
    km = KeyManager("stable-passphrase-1234")
    blob = km.encrypt(b"")
    assert km.decrypt(blob) == b""
