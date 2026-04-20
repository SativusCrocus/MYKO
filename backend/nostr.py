"""NostrClient — NIP-01 signing, NIP-13 proof-of-work, NIP-44 v2 encryption, NIP-17 gift-wrap.

* Keys are generated on first use and stored encrypted in the MYKO vault.
* Signatures use BIP-340 Schnorr via ``coincurve``.
* NIP-44 v2 implements ECDH (x-only) → HKDF-SHA256 → ChaCha20 + HMAC-SHA256.
* NIP-17 nests three envelopes: rumor (14) → seal (13) → gift-wrap (1059).
* Broadcast via ``websockets`` to multiple relays in parallel with per-relay timeouts.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Any

import websockets
from coincurve import PrivateKey, PublicKey, PublicKeyXOnly
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand

from .config import Settings
from .models import RelayResponse, SignedEvent, UnsignedEvent
from .vault import VaultManager

log = logging.getLogger("myko.nostr")

NIP44_VERSION = 0x02
NIP44_SALT = b"nip44-v2"
RELAY_TIMEOUT_SECONDS = 10
POW_MAX_ITERATIONS = 1 << 24  # bail after ~16M attempts


class NostrError(Exception):
    pass


# ----------------------------------------------------------- low-level helpers


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _count_leading_zero_bits(data: bytes) -> int:
    n = 0
    for byte in data:
        if byte == 0:
            n += 8
            continue
        mask = 0x80
        while mask and not (byte & mask):
            n += 1
            mask >>= 1
        break
    return n


def _xonly_to_pubkey(xonly_hex: str) -> PublicKey:
    """Lift an x-only (32-byte) hex pubkey to a full compressed PublicKey."""
    if len(xonly_hex) != 64:
        raise NostrError(f"x-only pubkey must be 32 bytes hex (got {len(xonly_hex)} chars)")
    try:
        x_bytes = bytes.fromhex(xonly_hex)
    except ValueError as e:
        raise NostrError(f"invalid hex pubkey: {e}") from e
    # Per BIP-340, x-only pubkeys have implicit even y.
    return PublicKey(b"\x02" + x_bytes)


def _ecdh_shared_x(priv: PrivateKey, recipient_xonly_hex: str) -> bytes:
    """Return the 32-byte x-coordinate of the ECDH shared point."""
    pub = _xonly_to_pubkey(recipient_xonly_hex)
    shared = pub.multiply(priv.secret)
    return shared.format(compressed=True)[1:33]


def _derive_conversation_key(priv: PrivateKey, recipient_xonly_hex: str) -> bytes:
    shared_x = _ecdh_shared_x(priv, recipient_xonly_hex)
    return hmac.new(NIP44_SALT, shared_x, hashlib.sha256).digest()


def _derive_message_keys(conversation_key: bytes, nonce: bytes) -> tuple[bytes, bytes, bytes]:
    """HKDF-Expand the conversation key using the per-message nonce into (chacha_key, chacha_nonce, hmac_key)."""
    hkdf = HKDFExpand(algorithm=hashes.SHA256(), length=76, info=nonce)
    material = hkdf.derive(conversation_key)
    return material[:32], material[32:44], material[44:76]


def _calc_padded_len(unpadded_len: int) -> int:
    """NIP-44 v2 ``calc_padded_len``: chunk-based padding, not naive power-of-two.

    For len <= 32, pad to 32. Otherwise, round up to the next multiple of
    ``chunk``, where ``chunk`` is 32 for the 33..256 range and
    ``next_power_of_two(len) // 8`` thereafter.
    """
    if unpadded_len <= 32:
        return 32
    next_power = 1 << (unpadded_len - 1).bit_length()
    chunk = 32 if next_power <= 256 else next_power // 8
    return chunk * ((unpadded_len - 1) // chunk + 1)


def _pad_plaintext(plaintext: bytes) -> bytes:
    """2-byte big-endian length prefix + zero padding to NIP-44 v2 bucket size."""
    n = len(plaintext)
    if n < 1 or n > 65535:
        raise NostrError(f"plaintext length {n} outside NIP-44 bounds (1..65535)")
    pad_len = _calc_padded_len(n) - n
    return n.to_bytes(2, "big") + plaintext + b"\x00" * pad_len


def _unpad_plaintext(padded: bytes) -> bytes:
    """Extract plaintext from a padded buffer, strictly validating NIP-44 v2 shape.

    Rejects: short headers, declared lengths that don't fit, buckets that
    don't match ``calc_padded_len``, and non-zero padding bytes.
    """
    if len(padded) < 2:
        raise NostrError("padded plaintext too short")
    n = int.from_bytes(padded[:2], "big")
    if n < 1 or n > 65535:
        raise NostrError("invalid padded length header")
    if 2 + n > len(padded):
        raise NostrError("declared length exceeds padded buffer")
    # Full padded length must equal 2 + calc_padded_len(n) — anything else is
    # malformed or a padding-oracle probe.
    if len(padded) != 2 + _calc_padded_len(n):
        raise NostrError("padded length does not match NIP-44 bucket size")
    if padded[2 + n :] != b"\x00" * (len(padded) - 2 - n):
        raise NostrError("non-zero padding bytes")
    return padded[2 : 2 + n]


def _chacha20_xor(key: bytes, nonce_12: bytes, data: bytes) -> bytes:
    # Our HKDF expands a 12-byte nonce. cryptography's ChaCha20 requires a 16-byte nonce
    # (4-byte counter || 12-byte nonce), so prepend zero counter per RFC 7539.
    full_nonce = b"\x00\x00\x00\x00" + nonce_12
    cipher = Cipher(algorithms.ChaCha20(key, full_nonce), mode=None)
    enc = cipher.encryptor()
    return enc.update(data) + enc.finalize()


# ------------------------------------------------------------- NIP-44 payload


def nip44_encrypt(
    priv_bytes: bytes,
    recipient_xonly_hex: str,
    plaintext: str,
    *,
    _nonce: bytes | None = None,
) -> str:
    """Produce a NIP-44 v2 base64-encoded ciphertext envelope.

    ``_nonce`` overrides the random nonce and is intended only for reproducing
    official test vectors; callers in production must let it default.
    """
    priv = PrivateKey(priv_bytes)
    conversation_key = _derive_conversation_key(priv, recipient_xonly_hex)
    nonce = _nonce if _nonce is not None else secrets.token_bytes(32)
    if len(nonce) != 32:
        raise NostrError(f"NIP-44 nonce must be 32 bytes (got {len(nonce)})")
    chacha_key, chacha_nonce, hmac_key = _derive_message_keys(conversation_key, nonce)
    padded = _pad_plaintext(plaintext.encode("utf-8"))
    ciphertext = _chacha20_xor(chacha_key, chacha_nonce, padded)
    mac = hmac.new(hmac_key, nonce + ciphertext, hashlib.sha256).digest()
    blob = bytes([NIP44_VERSION]) + nonce + ciphertext + mac
    import base64

    return base64.b64encode(blob).decode("ascii")


def nip44_decrypt(priv_bytes: bytes, sender_xonly_hex: str, payload_b64: str) -> str:
    import base64

    blob = base64.b64decode(payload_b64, validate=True)
    if len(blob) < 1 + 32 + 1 + 32:
        raise NostrError("NIP-44 payload too short")
    if blob[0] != NIP44_VERSION:
        raise NostrError(f"Unsupported NIP-44 version: {blob[0]}")
    nonce = blob[1:33]
    mac = blob[-32:]
    ciphertext = blob[33:-32]
    priv = PrivateKey(priv_bytes)
    conversation_key = _derive_conversation_key(priv, sender_xonly_hex)
    chacha_key, chacha_nonce, hmac_key = _derive_message_keys(conversation_key, nonce)
    expected_mac = hmac.new(hmac_key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected_mac):
        raise NostrError("NIP-44 MAC verification failed")
    padded = _chacha20_xor(chacha_key, chacha_nonce, ciphertext)
    return _unpad_plaintext(padded).decode("utf-8")


# ----------------------------------------------------------------- main client


class NostrClient:
    """Signs, broadcasts, and encrypts Nostr events on behalf of the user.

    The secp256k1 private key is stored encrypted in the vault on first use and
    loaded on demand; it is never cached plaintext between operations.
    """

    def __init__(self, vault: VaultManager, config: Settings):
        self._vault = vault
        self._config = config

    # ------------------------------------------------------------------ keys

    async def _load_or_create_privkey(self) -> bytes:
        entry = await self._vault.find_by_filename(self._config.NOSTR_KEY_FILENAME)
        if entry is not None:
            data = await self._vault.retrieve(entry.cid)
            if len(data) != 32:
                raise NostrError(f"Stored Nostr key has wrong length: {len(data)}")
            return data
        fresh = PrivateKey().secret
        await self._vault.store(self._config.NOSTR_KEY_FILENAME, fresh)
        log.info("Generated new Nostr keypair and stored in vault")
        return fresh

    async def get_pubkey(self) -> str:
        priv_bytes = await self._load_or_create_privkey()
        try:
            xonly = PublicKeyXOnly.from_secret(priv_bytes)
            return xonly.format().hex()
        finally:
            priv_bytes = b"\x00" * 32  # noqa: F841 (best-effort wipe of local reference)

    # ----------------------------------------------------------- event build

    @staticmethod
    def _event_id(pubkey: str, created_at: int, kind: int, tags: list[list[str]], content: str) -> str:
        unsigned = UnsignedEvent(pubkey=pubkey, created_at=created_at, kind=kind, tags=tags, content=content)
        return _sha256(unsigned.serialize().encode("utf-8")).hex()

    def _sign_event_id(self, priv_bytes: bytes, event_id_hex: str) -> str:
        priv = PrivateKey(priv_bytes)
        sig = priv.sign_schnorr(bytes.fromhex(event_id_hex))
        return sig.hex()

    async def create_event(
        self,
        kind: int,
        content: str,
        tags: list[list[str]] | None = None,
        pow_target: int | None = None,
    ) -> SignedEvent:
        tags = list(tags or [])
        priv_bytes = await self._load_or_create_privkey()
        pubkey = PublicKeyXOnly.from_secret(priv_bytes).format().hex()
        created_at = int(time.time())

        event_id = self._event_id(pubkey, created_at, kind, tags, content)

        if pow_target and pow_target > 0:
            # Strip any pre-existing nonce tags and search for a qualifying event id.
            base_tags = [t for t in tags if not (t and t[0] == "nonce")]
            nonce = 0
            while nonce < POW_MAX_ITERATIONS:
                pow_tags = base_tags + [["nonce", str(nonce), str(pow_target)]]
                event_id = self._event_id(pubkey, created_at, kind, pow_tags, content)
                if _count_leading_zero_bits(bytes.fromhex(event_id)) >= pow_target:
                    tags = pow_tags
                    break
                nonce += 1
            else:
                raise NostrError(
                    f"PoW target of {pow_target} bits not reached after {POW_MAX_ITERATIONS} iterations"
                )

        sig = self._sign_event_id(priv_bytes, event_id)
        return SignedEvent(
            id=event_id,
            pubkey=pubkey,
            created_at=created_at,
            kind=kind,
            tags=tags,
            content=content,
            sig=sig,
        )

    # ------------------------------------------------------------ broadcast

    async def _send_to_relay(self, relay_url: str, event_dict: dict[str, Any]) -> RelayResponse:
        frame = json.dumps(["EVENT", event_dict], separators=(",", ":"))
        try:
            async with websockets.connect(relay_url, open_timeout=RELAY_TIMEOUT_SECONDS) as ws:
                await asyncio.wait_for(ws.send(frame), timeout=RELAY_TIMEOUT_SECONDS)
                deadline = asyncio.get_event_loop().time() + RELAY_TIMEOUT_SECONDS
                while True:
                    remaining = deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        return RelayResponse(relay_url=relay_url, accepted=False, message="timeout waiting for OK")
                    raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(msg, list) and len(msg) >= 3 and msg[0] == "OK" and msg[1] == event_dict["id"]:
                        accepted = bool(msg[2])
                        message = msg[3] if len(msg) >= 4 and isinstance(msg[3], str) else ""
                        return RelayResponse(relay_url=relay_url, accepted=accepted, message=message)
        except (OSError, asyncio.TimeoutError, websockets.WebSocketException) as e:
            return RelayResponse(relay_url=relay_url, accepted=False, message=f"{type(e).__name__}: {e}")

    async def broadcast(self, event: SignedEvent, relays: list[str] | None = None) -> list[RelayResponse]:
        targets = relays or self._config.NOSTR_RELAYS
        if not targets:
            raise NostrError("No relays configured")
        tasks = [self._send_to_relay(url, event.to_dict()) for url in targets]
        return await asyncio.gather(*tasks)

    # ------------------------------------------------------------- NIP-17 DM

    async def send_dm(
        self, recipient_pubkey: str, plaintext: str
    ) -> tuple[str, list[RelayResponse]]:
        """NIP-17 gift-wrapped DM: rumor (14) → seal (13) → gift-wrap (1059)."""
        priv_bytes = await self._load_or_create_privkey()
        sender_pub = PublicKeyXOnly.from_secret(priv_bytes).format().hex()
        now = int(time.time())

        # 1. Rumor (kind 14) — unsigned.
        rumor: dict[str, Any] = {
            "pubkey": sender_pub,
            "created_at": now,
            "kind": 14,
            "tags": [["p", recipient_pubkey]],
            "content": plaintext,
        }
        rumor["id"] = self._event_id(sender_pub, now, 14, rumor["tags"], plaintext)
        rumor_json = json.dumps(rumor, separators=(",", ":"))

        # 2. Seal (kind 13) — signed by sender, NIP-44 encrypted to recipient.
        seal_content = nip44_encrypt(priv_bytes, recipient_pubkey, rumor_json)
        seal_event = await self._sign_raw(priv_bytes, sender_pub, 13, [], seal_content, timestamp=now)
        seal_json = json.dumps(seal_event.to_dict(), separators=(",", ":"))

        # 3. Gift-wrap (kind 1059) — signed by a throwaway key.
        throwaway_bytes = PrivateKey().secret
        throwaway_pub = PublicKeyXOnly.from_secret(throwaway_bytes).format().hex()
        gift_content = nip44_encrypt(throwaway_bytes, recipient_pubkey, seal_json)
        gift_event = await self._sign_raw(
            throwaway_bytes,
            throwaway_pub,
            1059,
            [["p", recipient_pubkey]],
            gift_content,
            timestamp=now,
        )

        responses = await self.broadcast(gift_event)
        return gift_event.id, responses

    async def _sign_raw(
        self,
        priv_bytes: bytes,
        pubkey: str,
        kind: int,
        tags: list[list[str]],
        content: str,
        timestamp: int | None = None,
    ) -> SignedEvent:
        ts = timestamp if timestamp is not None else int(time.time())
        event_id = self._event_id(pubkey, ts, kind, tags, content)
        sig = self._sign_event_id(priv_bytes, event_id)
        return SignedEvent(
            id=event_id,
            pubkey=pubkey,
            created_at=ts,
            kind=kind,
            tags=tags,
            content=content,
            sig=sig,
        )
