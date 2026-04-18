"""StorageEngine: mock Kubo /add, /cat, verify retry/timeout behavior."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from backend.storage import MAX_ATTEMPTS, StorageEngine, StorageError


class _FakeResponse:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self._body = body

    async def read(self) -> bytes:
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    """Minimal ``ClientSession`` stand-in that returns preprogrammed responses."""

    def __init__(self, responses: list[_FakeResponse | Exception]):
        self._responses = list(responses)
        self.posts: list[tuple[str, object]] = []

    def post(self, url, data=None):
        self.posts.append((url, data))
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self):
        return None


def _install_session(engine: StorageEngine, session) -> None:
    engine._session = session  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_pin_file_returns_last_hash():
    engine = StorageEngine("http://127.0.0.1:5001/api/v0")
    body = b'{"Name":"blob","Hash":"QmABC","Size":"5"}\n'
    _install_session(engine, _FakeSession([_FakeResponse(200, body)]))
    cid = await engine.pin_file(b"hello")
    assert cid == "QmABC"


@pytest.mark.asyncio
async def test_fetch_returns_bytes():
    engine = StorageEngine("http://127.0.0.1:5001/api/v0")
    _install_session(engine, _FakeSession([_FakeResponse(200, b"payload-bytes")]))
    data = await engine.fetch("QmZZZ")
    assert data == b"payload-bytes"


@pytest.mark.asyncio
async def test_http_error_raises_storage_error():
    engine = StorageEngine("http://127.0.0.1:5001/api/v0")
    _install_session(engine, _FakeSession([_FakeResponse(500, b"kubo down")] * MAX_ATTEMPTS))
    with pytest.raises(StorageError):
        await engine.fetch("QmZZZ")


@pytest.mark.asyncio
async def test_retries_on_client_error_then_succeeds(monkeypatch):
    engine = StorageEngine("http://127.0.0.1:5001/api/v0")
    fake = _FakeSession(
        [
            aiohttp.ClientError("conn reset"),
            _FakeResponse(200, b"ok"),
        ]
    )
    _install_session(engine, fake)
    # Patch sleep to skip the 1s backoff in tests
    sleeps: list[float] = []

    async def _fast_sleep(d):
        sleeps.append(d)

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)
    data = await engine.fetch("QmZZZ")
    assert data == b"ok"
    assert sleeps == [1]  # one backoff between the two attempts


@pytest.mark.asyncio
async def test_gives_up_after_max_attempts(monkeypatch):
    engine = StorageEngine("http://127.0.0.1:5001/api/v0")
    fake = _FakeSession([aiohttp.ClientError("down")] * MAX_ATTEMPTS)
    _install_session(engine, fake)

    async def _fast_sleep(d):
        return None

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)
    with pytest.raises(StorageError):
        await engine.fetch("Qm")


@pytest.mark.asyncio
async def test_pin_directory_rejects_missing_path():
    engine = StorageEngine("http://127.0.0.1:5001/api/v0")
    _install_session(engine, _FakeSession([]))
    with pytest.raises(StorageError):
        await engine.pin_directory("/nonexistent/path/for/testing")


@pytest.mark.asyncio
async def test_pin_directory_rejects_empty_directory(tmp_path):
    engine = StorageEngine("http://127.0.0.1:5001/api/v0")
    _install_session(engine, _FakeSession([]))
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(StorageError):
        await engine.pin_directory(str(empty))


@pytest.mark.asyncio
async def test_pin_directory_returns_root_cid(tmp_path):
    engine = StorageEngine("http://127.0.0.1:5001/api/v0")
    d = tmp_path / "project"
    d.mkdir()
    (d / "a.txt").write_text("a")
    (d / "b.txt").write_text("b")
    body = (
        b'{"Name":"a.txt","Hash":"QmA"}\n'
        b'{"Name":"b.txt","Hash":"QmB"}\n'
        b'{"Name":"project","Hash":"QmROOT"}\n'
    )
    _install_session(engine, _FakeSession([_FakeResponse(200, body)]))
    cid = await engine.pin_directory(str(d))
    assert cid == "QmROOT"


@pytest.mark.asyncio
async def test_context_manager_closes_session():
    async with StorageEngine("http://127.0.0.1:5001/api/v0") as engine:
        assert engine._session is not None
    assert engine._session is None
