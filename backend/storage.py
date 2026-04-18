"""StorageEngine: async Kubo (IPFS) RPC client with retry/backoff."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

import aiohttp

log = logging.getLogger("myko.storage")

DEFAULT_TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 3


class StorageError(Exception):
    """Raised on Kubo RPC failures (network, HTTP error, malformed response)."""


class StorageEngine:
    """Async client for the Kubo HTTP RPC at ``/api/v0/*``.

    Use as an async context manager to own the ``aiohttp.ClientSession`` lifecycle::

        async with StorageEngine(url) as storage:
            cid = await storage.pin_file(b"...")
    """

    def __init__(self, api_url: str):
        self.api_url = api_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "StorageEngine":
        timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT_SECONDS)
        self._session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise StorageError("StorageEngine not initialized (use `async with`)")
        return self._session

    async def _post(self, url: str, *, data=None) -> bytes:
        last_err: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                async with self.session.post(url, data=data) as resp:
                    body = await resp.read()
                    if resp.status != 200:
                        raise StorageError(
                            f"Kubo {resp.status} at {url}: {body[:200].decode('utf-8', 'replace')}"
                        )
                    return body
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_err = e
                if attempt < MAX_ATTEMPTS - 1:
                    backoff = 2**attempt  # 1, 2, 4 seconds
                    log.warning(f"Kubo request failed (attempt {attempt + 1}/{MAX_ATTEMPTS}): {e}; retrying in {backoff}s")
                    await asyncio.sleep(backoff)
        raise StorageError(f"Kubo request to {url} failed after {MAX_ATTEMPTS} attempts: {last_err}")

    @staticmethod
    def _parse_add_lines(body: bytes) -> list[dict]:
        """Parse Kubo's newline-delimited JSON response from ``/add``."""
        out: list[dict] = []
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise StorageError(f"Malformed Kubo response line: {line!r}: {e}")
        if not out:
            raise StorageError("Kubo /add returned empty response")
        return out

    async def pin_file(self, data: bytes) -> str:
        """POST a single blob to ``/add`` and return its CID."""
        form = aiohttp.FormData()
        form.add_field("file", data, filename="blob", content_type="application/octet-stream")
        body = await self._post(f"{self.api_url}/add?pin=true", data=form)
        entries = self._parse_add_lines(body)
        last = entries[-1]
        if "Hash" not in last:
            raise StorageError(f"Kubo /add response missing Hash: {last}")
        return last["Hash"]

    async def pin_directory(self, path: str) -> str:
        """Hash and pin a local directory tree; return the root CID.

        Uses Kubo's ``recursive=true&wrap-with-directory=true`` mode with a
        multipart form where each file is added with its path relative to the
        directory root as the filename.
        """
        root = Path(path)
        if not root.exists():
            raise StorageError(f"Path does not exist: {path}")
        if not root.is_dir():
            raise StorageError(f"Not a directory: {path}")

        form = aiohttp.FormData()
        file_count = 0
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                fp = Path(dirpath) / name
                rel = fp.relative_to(root)
                with open(fp, "rb") as fh:
                    form.add_field(
                        "file",
                        fh.read(),
                        filename=str(rel),
                        content_type="application/octet-stream",
                    )
                file_count += 1

        if file_count == 0:
            raise StorageError(f"Directory contains no files: {path}")

        body = await self._post(
            f"{self.api_url}/add?recursive=true&wrap-with-directory=true&pin=true",
            data=form,
        )
        entries = self._parse_add_lines(body)
        root_cid = entries[-1].get("Hash")
        if not root_cid:
            raise StorageError(f"Could not determine root CID from Kubo response: {entries[-1]}")
        return root_cid

    async def fetch(self, cid: str) -> bytes:
        """Retrieve raw bytes for a CID via ``/cat``."""
        if not cid:
            raise StorageError("CID must be non-empty")
        return await self._post(f"{self.api_url}/cat?arg={cid}")
