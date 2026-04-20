"""FastAPI HTTP bridge — the Tauri-facing interface (separate process from the MCP server).

Run with: ``python -m backend.bridge``

Characteristics:
  * Binds only to ``127.0.0.1`` (never ``0.0.0.0``).
  * CORS restricted to origin ``tauri://localhost``.
  * Every request must carry ``Authorization: Bearer <session_token>`` where the
    token is a random 64-char hex string written to ``~/MYKO/.session_token``
    with mode 0600 at bridge startup.
  * Instantiates its own KeyManager / StorageEngine / VaultManager / NostrClient /
    LightningWallet. Concurrent access to ``manifest.enc`` is serialized with
    ``fcntl.flock`` inside ``VaultManager``.
  * Reads the MCP server's ``~/MYKO/.goose_status.json`` for the /goose/status endpoint.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
import websockets
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import Settings
from .crypto import KeyManager
from .logging_config import configure_logging
from .security import constant_time_compare
from .storage import StorageEngine
from .vault import VaultManager

log = logging.getLogger("myko.bridge")


class _AppState:
    settings: Settings
    key_mgr: KeyManager
    storage: StorageEngine
    vault: VaultManager
    nostr: Any  # NostrClient | None
    wallet: Any  # LightningWallet | None
    session_token: str


state = _AppState()


def _write_session_token(home: Path) -> str:
    home.mkdir(parents=True, exist_ok=True)
    token_path = home / ".session_token"
    token = secrets.token_hex(32)
    fd = os.open(str(token_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(token)
    return token


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings = Settings()
    configure_logging(settings.MYKO_HOME, settings.LOG_LEVEL)
    state.settings = settings
    state.key_mgr = KeyManager(settings.MYKO_PASSPHRASE, yubikey_enabled=settings.YUBIKEY_ENABLED)

    state.storage = StorageEngine(settings.IPFS_API_URL)
    await state.storage.__aenter__()
    state.vault = VaultManager(state.key_mgr, state.storage, settings.MYKO_HOME)

    try:
        from .nostr import NostrClient

        state.nostr = NostrClient(state.vault, settings)
    except Exception as e:
        log.warning(f"Nostr not available: {e}")
        state.nostr = None

    try:
        from .lightning import LightningWallet

        state.wallet = LightningWallet.create(settings)
        await state.wallet.__aenter__()
    except Exception as e:
        log.warning(f"Lightning not available: {e}")
        state.wallet = None

    state.session_token = _write_session_token(settings.MYKO_HOME)
    log.info(f"Bridge session token written to {settings.MYKO_HOME / '.session_token'} (mode 0600)")
    try:
        yield
    finally:
        await state.storage.close()
        if state.wallet is not None:
            await state.wallet.close()


app = FastAPI(lifespan=_lifespan, title="MYKO Bridge", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["tauri://localhost"],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=False,
)


# ------------------------------------------------------------ auth dependency


async def require_token(authorization: str | None = Header(default=None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    presented = authorization.removeprefix("Bearer ").strip()
    if not constant_time_compare(presented, state.session_token):
        raise HTTPException(status_code=401, detail="Invalid session token")


# --------------------------------------------------------------- request body


class VaultStoreRequest(BaseModel):
    filename: str
    content: str  # base64


class VaultRetrieveRequest(BaseModel):
    cid: str


# ------------------------------------------------------------------ endpoints


@app.get("/vault/list", dependencies=[Depends(require_token)])
async def vault_list():
    entries = await state.vault.list()
    return {"entries": [e.model_dump(mode="json") for e in entries]}


@app.post("/vault/store", dependencies=[Depends(require_token)])
async def vault_store(req: VaultStoreRequest):
    try:
        data = base64.b64decode(req.content, validate=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64: {e}") from e
    entry = await state.vault.store(req.filename, data)
    return {
        "cid": entry.cid,
        "filename": entry.filename,
        "size_bytes": entry.size_bytes,
        "stored_at": entry.stored_at.isoformat(),
    }


@app.post("/vault/retrieve", dependencies=[Depends(require_token)])
async def vault_retrieve(req: VaultRetrieveRequest):
    plaintext = await state.vault.retrieve(req.cid)
    match = await state.vault.find_by_cid(req.cid)
    filename = match.filename if match else "unknown"
    return {
        "filename": filename,
        "content": base64.b64encode(plaintext).decode("ascii"),
        "size_bytes": len(plaintext),
    }


@app.get("/lightning/balance", dependencies=[Depends(require_token)])
async def lightning_balance():
    if state.wallet is None:
        raise HTTPException(status_code=503, detail="Lightning not configured")
    try:
        sats = await state.wallet.get_balance()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Lightning upstream error: {e}") from e
    return {"balance_sats": int(sats)}


RELAY_PROBE_TIMEOUT_SECONDS = 3


async def _probe_relay(url: str) -> bool:
    """Return True if we can open a WebSocket to ``url`` within the probe timeout."""
    try:
        async with asyncio.timeout(RELAY_PROBE_TIMEOUT_SECONDS):
            async with websockets.connect(url, open_timeout=RELAY_PROBE_TIMEOUT_SECONDS):
                return True
    except (OSError, asyncio.TimeoutError, websockets.WebSocketException, Exception):
        return False


@app.get("/identity/info", dependencies=[Depends(require_token)])
async def identity_info():
    if state.nostr is None:
        raise HTTPException(status_code=503, detail="Nostr not configured")
    pubkey_hex = await state.nostr.get_pubkey()
    npub = _xonly_hex_to_npub(pubkey_hex)
    relays = state.settings.NOSTR_RELAYS
    statuses = await asyncio.gather(*(_probe_relay(u) for u in relays), return_exceptions=False)
    return {
        "pubkey_hex": pubkey_hex,
        "npub": npub,
        "relays": [{"url": u, "connected": bool(s)} for u, s in zip(relays, statuses)],
        "last_broadcast": None,
    }


def _tail_lines(path: Path, n: int, chunk_size: int = 8192) -> list[str]:
    """Return the last ``n`` lines of a file without loading it fully into memory.

    Seeks to EOF and reads backward in ``chunk_size`` blocks until ``n`` newlines
    are found (or the start of the file is reached). Trailing empty lines are
    preserved by ``splitlines()`` behavior of the final decode.
    """
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        if size == 0:
            return []
        pos = size
        newline_count = 0
        chunks: list[bytes] = []
        while pos > 0 and newline_count <= n:
            read = min(chunk_size, pos)
            pos -= read
            f.seek(pos)
            buf = f.read(read)
            chunks.append(buf)
            newline_count += buf.count(b"\n")
        data = b"".join(reversed(chunks))
    # Decode leniently; audit logs are UTF-8 but we don't want a single bad byte
    # to break the whole tail view.
    lines = data.decode("utf-8", errors="replace").splitlines()
    return lines[-n:]


@app.get("/audit/recent", dependencies=[Depends(require_token)])
async def audit_recent(limit: int = Query(default=50, ge=1, le=500)):
    path = state.settings.MYKO_HOME / "logs" / "audit.jsonl"
    if not path.exists():
        return {"entries": []}
    lines = _tail_lines(path, limit)
    entries: list[dict] = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return {"entries": entries}


@app.get("/goose/status", dependencies=[Depends(require_token)])
async def goose_status():
    path = state.settings.MYKO_HOME / ".goose_status.json"
    if not path.exists():
        return {
            "connected": False,
            "pid": None,
            "uptime_seconds": 0,
            "last_tool_call": None,
            "total_calls": 0,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "connected": False,
            "pid": None,
            "uptime_seconds": 0,
            "last_tool_call": None,
            "total_calls": 0,
        }
    # Liveness check: if the recorded PID is still running, consider Goose connected.
    pid = data.get("pid")
    alive = False
    if isinstance(pid, int) and pid > 0:
        try:
            os.kill(pid, 0)
            alive = True
        except OSError:
            alive = False
    return {
        "connected": alive,
        "pid": pid,
        "uptime_seconds": data.get("uptime_seconds", 0),
        "last_tool_call": {
            "tool": data.get("last_tool"),
            "ts": data.get("last_tool_ts"),
        }
        if data.get("last_tool")
        else None,
        "total_calls": data.get("total_calls", 0),
    }


@app.get("/health")
async def health():
    # Unauthenticated liveness probe — reports only the bridge process itself.
    return {"ok": True, "ts": datetime.now(timezone.utc).isoformat()}


# ------------------------------------------------------------------ helpers


_BECH32_ALPHABET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _bech32_polymod(values: list[int]) -> int:
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            chk ^= gen[i] if ((b >> i) & 1) else 0
    return chk


def _bech32_hrp_expand(hrp: str) -> list[int]:
    return [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]


def _bech32_create_checksum(hrp: str, data: list[int]) -> list[int]:
    values = _bech32_hrp_expand(hrp) + data
    polymod = _bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ 1
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]


def _convertbits(data: bytes, frombits: int, tobits: int, pad: bool = True) -> list[int]:
    acc = 0
    bits = 0
    ret: list[int] = []
    maxv = (1 << tobits) - 1
    maxacc = (1 << (frombits + tobits - 1)) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            raise ValueError("invalid data for base conversion")
        acc = ((acc << frombits) | value) & maxacc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad and bits:
        ret.append((acc << (tobits - bits)) & maxv)
    return ret


def _xonly_hex_to_npub(hex_pubkey: str) -> str:
    """Encode a 32-byte x-only pubkey as a bech32 ``npub1...`` string (NIP-19)."""
    data = _convertbits(bytes.fromhex(hex_pubkey), 8, 5, pad=True)
    checksum = _bech32_create_checksum("npub", data)
    combined = data + checksum
    return "npub" + "1" + "".join(_BECH32_ALPHABET[c] for c in combined)


# ------------------------------------------------------------------ entrypoint


def main() -> None:
    settings = Settings()
    uvicorn.run(
        "backend.bridge:app",
        host="127.0.0.1",
        port=settings.BRIDGE_PORT,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=False,
        reload=False,
    )


if __name__ == "__main__":
    main()
