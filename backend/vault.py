"""VaultManager: encrypt-before-store, encrypted manifest with OS file locking.

Data flow on store:
    plaintext  →  KeyManager.encrypt  →  StorageEngine.pin_file  →  CID
    append ManifestEntry(filename, cid, size_bytes, stored_at)  →  manifest.enc

Data flow on retrieve:
    CID  →  StorageEngine.fetch  →  KeyManager.decrypt  →  plaintext

The manifest itself is AES-256-GCM encrypted and protected by ``fcntl.flock``
so the MCP server and bridge processes can share the file safely.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .crypto import CryptoError, KeyManager
from .storage import StorageEngine

log = logging.getLogger("myko.vault")


class ManifestEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    filename: str
    cid: str
    size_bytes: int
    stored_at: datetime


class VaultError(Exception):
    pass


class VaultManager:
    def __init__(self, key_mgr: KeyManager, storage: StorageEngine, home: Path):
        self.key_mgr = key_mgr
        self.storage = storage
        self.home = Path(home).expanduser()
        self.home.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.home / "manifest.enc"

    def _read_manifest_sync(self) -> list[ManifestEntry]:
        if not self.manifest_path.exists():
            return []
        with open(self.manifest_path, "rb") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                blob = f.read()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        if not blob:
            return []
        try:
            plaintext = self.key_mgr.decrypt(blob)
        except CryptoError as e:
            raise VaultError(f"Manifest decryption failed: {e}") from e
        try:
            raw = json.loads(plaintext.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise VaultError(f"Manifest JSON parse failed: {e}") from e
        return [ManifestEntry(**e) for e in raw]

    def _write_manifest_sync(self, entries: list[ManifestEntry]) -> None:
        data = json.dumps(
            [e.model_dump(mode="json") for e in entries],
            separators=(",", ":"),
        ).encode("utf-8")
        blob = self.key_mgr.encrypt(data)

        tmp_path = self.manifest_path.with_name(self.manifest_path.name + ".tmp")
        fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(blob)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        os.replace(str(tmp_path), str(self.manifest_path))

    async def list(self) -> list[ManifestEntry]:
        return await asyncio.to_thread(self._read_manifest_sync)

    async def store(self, filename: str, content: bytes) -> ManifestEntry:
        if not filename:
            raise VaultError("filename must be non-empty")
        ciphertext = self.key_mgr.encrypt(content)
        cid = await self.storage.pin_file(ciphertext)
        entry = ManifestEntry(
            filename=filename,
            cid=cid,
            size_bytes=len(content),
            stored_at=datetime.now(timezone.utc),
        )

        def _append() -> None:
            entries = self._read_manifest_sync()
            entries.append(entry)
            self._write_manifest_sync(entries)

        await asyncio.to_thread(_append)
        log.info(f"Vault stored {filename} as {cid} ({len(content)} bytes)")
        return entry

    async def retrieve(self, cid: str) -> bytes:
        if not cid:
            raise VaultError("CID must be non-empty")
        ciphertext = await self.storage.fetch(cid)
        try:
            return self.key_mgr.decrypt(ciphertext)
        except CryptoError as e:
            raise VaultError(f"Vault retrieve failed for {cid}: {e}") from e

    async def find_by_filename(self, filename: str) -> ManifestEntry | None:
        for entry in await self.list():
            if entry.filename == filename:
                return entry
        return None

    async def find_by_cid(self, cid: str) -> ManifestEntry | None:
        for entry in await self.list():
            if entry.cid == cid:
                return entry
        return None
