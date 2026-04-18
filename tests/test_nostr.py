"""NostrClient: NIP-01 sign/verify, NIP-13 PoW, NIP-44 roundtrip, NIP-17 envelope."""

from __future__ import annotations

import hashlib
import json
from unittest.mock import AsyncMock, patch

import pytest
from coincurve import PrivateKey, PublicKeyXOnly

from backend.config import Settings
from backend.crypto import KeyManager
from backend.models import UnsignedEvent
from backend.nostr import (
    NIP44_VERSION,
    NostrClient,
    NostrError,
    _count_leading_zero_bits,
    _pad_plaintext,
    _unpad_plaintext,
    nip44_decrypt,
    nip44_encrypt,
)
from backend.vault import VaultManager
from tests.test_vault import FakeStorage


# --------------------------------------------------------- fixtures / helpers


def _make_settings(tmp_path) -> Settings:
    return Settings(
        MYKO_PASSPHRASE="test-passphrase-1234",
        MYKO_HOME=tmp_path,
    )


async def _make_client(tmp_path) -> NostrClient:
    settings = _make_settings(tmp_path)
    km = KeyManager(settings.MYKO_PASSPHRASE)
    vault = VaultManager(km, FakeStorage(), tmp_path)
    return NostrClient(vault, settings)


# ----------------------------------------------------------- NIP-01 signing


def test_unsigned_event_serialize_is_canonical():
    evt = UnsignedEvent(
        pubkey="a" * 64,
        created_at=1_700_000_000,
        kind=1,
        tags=[["t", "hello"]],
        content="hi",
    )
    s = evt.serialize()
    assert s == '[0,"' + ("a" * 64) + '",1700000000,1,[["t","hello"]],"hi"]'


@pytest.mark.asyncio
async def test_create_event_signature_verifies(tmp_path):
    client = await _make_client(tmp_path)
    event = await client.create_event(kind=1, content="hello world", tags=[])
    assert len(event.id) == 64
    assert len(event.sig) == 128
    # Verify Schnorr signature over the event id.
    xonly = PublicKeyXOnly(bytes.fromhex(event.pubkey))
    assert xonly.verify(bytes.fromhex(event.sig), bytes.fromhex(event.id))


@pytest.mark.asyncio
async def test_event_id_is_sha256_of_serialized(tmp_path):
    client = await _make_client(tmp_path)
    event = await client.create_event(kind=1, content="fingerprint", tags=[["x", "1"]])
    unsigned = UnsignedEvent(
        pubkey=event.pubkey,
        created_at=event.created_at,
        kind=event.kind,
        tags=event.tags,
        content=event.content,
    )
    expected = hashlib.sha256(unsigned.serialize().encode("utf-8")).hexdigest()
    assert event.id == expected


@pytest.mark.asyncio
async def test_pubkey_is_stable_after_first_use(tmp_path):
    client = await _make_client(tmp_path)
    a = await client.get_pubkey()
    b = await client.get_pubkey()
    assert a == b
    assert len(a) == 64


# ------------------------------------------------------------- NIP-13 PoW


def test_count_leading_zero_bits():
    assert _count_leading_zero_bits(b"\x00\xff") == 8
    assert _count_leading_zero_bits(b"\x80") == 0
    assert _count_leading_zero_bits(b"\x40") == 1
    assert _count_leading_zero_bits(b"\x01") == 7
    assert _count_leading_zero_bits(b"\x00\x00\x80") == 16


@pytest.mark.asyncio
async def test_pow_produces_required_leading_zero_bits(tmp_path):
    client = await _make_client(tmp_path)
    event = await client.create_event(kind=1, content="pow test", tags=[], pow_target=8)
    assert _count_leading_zero_bits(bytes.fromhex(event.id)) >= 8
    assert any(t[0] == "nonce" for t in event.tags)


# -------------------------------------------------------------- NIP-44 v2


def test_nip44_roundtrip_between_two_keypairs():
    alice = PrivateKey()
    bob = PrivateKey()
    alice_xonly = PublicKeyXOnly.from_secret(alice.secret).format().hex()
    bob_xonly = PublicKeyXOnly.from_secret(bob.secret).format().hex()

    plaintext = "Sovereign greetings — ⚡ 🔐"
    payload = nip44_encrypt(alice.secret, bob_xonly, plaintext)
    recovered = nip44_decrypt(bob.secret, alice_xonly, payload)
    assert recovered == plaintext


def test_nip44_version_byte_present():
    import base64

    alice = PrivateKey()
    bob = PrivateKey()
    bob_xonly = PublicKeyXOnly.from_secret(bob.secret).format().hex()
    payload = nip44_encrypt(alice.secret, bob_xonly, "hi")
    raw = base64.b64decode(payload)
    assert raw[0] == NIP44_VERSION
    # 1 + 32 nonce + at least 32 padded ciphertext + 32 mac
    assert len(raw) >= 1 + 32 + 32 + 32


def test_nip44_tamper_detection():
    import base64

    alice = PrivateKey()
    bob = PrivateKey()
    alice_xonly = PublicKeyXOnly.from_secret(alice.secret).format().hex()
    bob_xonly = PublicKeyXOnly.from_secret(bob.secret).format().hex()
    payload = nip44_encrypt(alice.secret, bob_xonly, "tamper me")
    raw = bytearray(base64.b64decode(payload))
    raw[40] ^= 0x01  # flip a bit in the ciphertext region
    tampered = base64.b64encode(bytes(raw)).decode("ascii")
    with pytest.raises(NostrError):
        nip44_decrypt(bob.secret, alice_xonly, tampered)


def test_nip44_padding_buckets_to_power_of_two():
    for n, expected_bucket in [(1, 32), (32, 32), (33, 64), (100, 128), (129, 256)]:
        padded = _pad_plaintext(b"x" * n)
        assert len(padded) == 2 + expected_bucket


def test_nip44_unpad_recovers_original_length():
    data = b"arbitrary bytes \x00\x01\xff"
    padded = _pad_plaintext(data)
    assert _unpad_plaintext(padded) == data


# -------------------------------------------------------------- NIP-17 DM


@pytest.mark.asyncio
async def test_nip17_dm_envelope_structure(tmp_path):
    client = await _make_client(tmp_path)
    recipient = PrivateKey()
    recipient_xonly = PublicKeyXOnly.from_secret(recipient.secret).format().hex()

    captured: dict = {}

    async def _fake_broadcast(event, relays=None):
        captured["event"] = event
        return []

    with patch.object(client, "broadcast", side_effect=_fake_broadcast):
        event_id, responses = await client.send_dm(recipient_xonly, "secret message")

    gift = captured["event"]
    assert gift.kind == 1059
    assert any(t[0] == "p" and t[1] == recipient_xonly for t in gift.tags)
    # Recipient can unwrap the seal, then the rumor.
    seal_json = nip44_decrypt(recipient.secret, gift.pubkey, gift.content)
    seal = json.loads(seal_json)
    assert seal["kind"] == 13
    rumor_json = nip44_decrypt(recipient.secret, seal["pubkey"], seal["content"])
    rumor = json.loads(rumor_json)
    assert rumor["kind"] == 14
    assert rumor["content"] == "secret message"
    assert event_id == gift.id


# ---------------------------------------------------------------- broadcast


@pytest.mark.asyncio
async def test_broadcast_handles_relay_failures_gracefully(tmp_path):
    client = await _make_client(tmp_path)
    event = await client.create_event(kind=1, content="hello", tags=[])

    async def _fail(relay_url, event_dict):
        from backend.models import RelayResponse

        if "broken" in relay_url:
            return RelayResponse(relay_url=relay_url, accepted=False, message="fail")
        return RelayResponse(relay_url=relay_url, accepted=True)

    with patch.object(client, "_send_to_relay", side_effect=_fail):
        responses = await client.broadcast(event, relays=["wss://ok.example", "wss://broken.example"])

    assert len(responses) == 2
    accepted = [r.accepted for r in responses]
    assert accepted == [True, False]
