"""VaultManager: store → list → retrieve cycle with an in-memory fake storage."""

from __future__ import annotations

import hashlib

import pytest

from backend.crypto import KeyManager
from backend.storage import StorageEngine
from backend.vault import VaultError, VaultManager


class FakeStorage(StorageEngine):
    """In-memory substitute that satisfies the ``pin_file``/``fetch`` contract."""

    def __init__(self):
        super().__init__("http://fake")
        self.store: dict[str, bytes] = {}

    async def pin_file(self, data: bytes) -> str:
        cid = "Qm" + hashlib.sha256(data).hexdigest()[:44]
        self.store[cid] = data
        return cid

    async def fetch(self, cid: str) -> bytes:
        if cid not in self.store:
            raise KeyError(cid)
        return self.store[cid]

    async def pin_directory(self, path: str) -> str:  # unused in vault tests
        raise NotImplementedError


@pytest.mark.asyncio
async def test_store_then_list_returns_entry(tmp_path):
    km = KeyManager("test-passphrase-1234")
    vault = VaultManager(km, FakeStorage(), tmp_path)
    entry = await vault.store("hello.txt", b"hello world")
    assert entry.filename == "hello.txt"
    assert entry.size_bytes == len(b"hello world")
    listing = await vault.list()
    assert len(listing) == 1
    assert listing[0].cid == entry.cid


@pytest.mark.asyncio
async def test_retrieve_roundtrips_plaintext(tmp_path):
    km = KeyManager("test-passphrase-1234")
    vault = VaultManager(km, FakeStorage(), tmp_path)
    entry = await vault.store("doc.bin", b"binary \x00\x01\x02 data")
    got = await vault.retrieve(entry.cid)
    assert got == b"binary \x00\x01\x02 data"


@pytest.mark.asyncio
async def test_retrieve_with_wrong_key_fails(tmp_path):
    km_a = KeyManager("passphrase-a-long-enough")
    storage = FakeStorage()
    vault_a = VaultManager(km_a, storage, tmp_path)
    entry = await vault_a.store("secret.txt", b"top secret")

    km_b = KeyManager("different-passphrase-b")
    vault_b = VaultManager(km_b, storage, tmp_path)
    # Manifest itself is encrypted with km_a's key, so list() should fail first
    with pytest.raises(VaultError):
        await vault_b.retrieve(entry.cid)


@pytest.mark.asyncio
async def test_multiple_stores_accumulate(tmp_path):
    km = KeyManager("test-passphrase-1234")
    vault = VaultManager(km, FakeStorage(), tmp_path)
    for i in range(5):
        await vault.store(f"f{i}.txt", f"content-{i}".encode())
    entries = await vault.list()
    assert len(entries) == 5
    assert [e.filename for e in entries] == [f"f{i}.txt" for i in range(5)]


@pytest.mark.asyncio
async def test_manifest_persists_across_instances(tmp_path):
    km = KeyManager("test-passphrase-1234")
    storage = FakeStorage()
    vault1 = VaultManager(km, storage, tmp_path)
    await vault1.store("persist.txt", b"across instances")

    vault2 = VaultManager(km, storage, tmp_path)
    entries = await vault2.list()
    assert len(entries) == 1
    assert entries[0].filename == "persist.txt"


@pytest.mark.asyncio
async def test_find_by_filename_and_cid(tmp_path):
    km = KeyManager("test-passphrase-1234")
    vault = VaultManager(km, FakeStorage(), tmp_path)
    entry = await vault.store("lookup.txt", b"data")
    assert (await vault.find_by_filename("lookup.txt")).cid == entry.cid
    assert (await vault.find_by_cid(entry.cid)).filename == "lookup.txt"
    assert await vault.find_by_filename("missing") is None
    assert await vault.find_by_cid("QmMissing") is None


@pytest.mark.asyncio
async def test_manifest_file_is_encrypted_on_disk(tmp_path):
    km = KeyManager("test-passphrase-1234")
    vault = VaultManager(km, FakeStorage(), tmp_path)
    await vault.store("needle.txt", b"haystack")
    raw = (tmp_path / "manifest.enc").read_bytes()
    assert b"needle.txt" not in raw
    assert b"haystack" not in raw


@pytest.mark.asyncio
async def test_empty_filename_rejected(tmp_path):
    km = KeyManager("test-passphrase-1234")
    vault = VaultManager(km, FakeStorage(), tmp_path)
    with pytest.raises(VaultError):
        await vault.store("", b"data")
