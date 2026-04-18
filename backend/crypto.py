"""KeyManager: PBKDF2-derived AES-256-GCM encryption with optional YubiKey hardware factor.

Ciphertext blob layout:
    salt (32 bytes) ‖ nonce (12 bytes) ‖ ciphertext ‖ tag (16 bytes)

The 16-byte AEAD tag is appended to the ciphertext by ``AESGCM.encrypt`` and
consumed by ``AESGCM.decrypt`` — we do not split it explicitly.
"""

from __future__ import annotations

import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .security import secure_wipe, yubikey_challenge

SALT_LEN = 32
NONCE_LEN = 12
KEY_LEN = 32
TAG_LEN = 16
PBKDF2_ITERATIONS = 600_000


class CryptoError(Exception):
    """Raised when decryption or key derivation fails."""


class KeyManager:
    """Derives ephemeral keys from a passphrase (+ optional YubiKey) for each operation.

    A new random salt is generated per ``encrypt`` call; the salt is embedded in
    the ciphertext so ``decrypt`` can re-derive the same key. Keys are never cached.
    """

    def __init__(self, passphrase: str, yubikey_enabled: bool = False):
        if not passphrase:
            raise CryptoError("Passphrase must not be empty")
        self._passphrase = passphrase.encode("utf-8")
        self.yubikey_enabled = yubikey_enabled

    def _derive_key(self, salt: bytes) -> bytearray:
        material = bytearray(self._passphrase)
        if self.yubikey_enabled:
            response = yubikey_challenge(salt)
            if response:
                material.extend(response)
        try:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=KEY_LEN,
                salt=salt,
                iterations=PBKDF2_ITERATIONS,
            )
            derived = kdf.derive(bytes(material))
            return bytearray(derived)
        finally:
            secure_wipe(material)

    def encrypt(self, plaintext: bytes) -> bytes:
        salt = os.urandom(SALT_LEN)
        nonce = os.urandom(NONCE_LEN)
        key = self._derive_key(salt)
        try:
            aesgcm = AESGCM(bytes(key))
            ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        finally:
            secure_wipe(key)
        return salt + nonce + ciphertext

    def decrypt(self, blob: bytes) -> bytes:
        if len(blob) < SALT_LEN + NONCE_LEN + TAG_LEN:
            raise CryptoError("Ciphertext blob is too short")
        salt = blob[:SALT_LEN]
        nonce = blob[SALT_LEN : SALT_LEN + NONCE_LEN]
        ct = blob[SALT_LEN + NONCE_LEN :]
        key = self._derive_key(salt)
        try:
            aesgcm = AESGCM(bytes(key))
            try:
                return aesgcm.decrypt(nonce, ct, None)
            except InvalidTag as e:
                raise CryptoError("Decryption failed: tag verification failed (wrong passphrase or corrupted data)") from e
        finally:
            secure_wipe(key)
