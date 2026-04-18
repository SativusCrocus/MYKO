# MYKO — Prompt Kit (Final)

> Local-first, decentralized Life OS. Goose is the brain. User owns every key. AI executes, never controls.

---

## HOW TO USE THIS FILE

- **Option A:** Use PROMPT 0 (consolidated) for a full single-shot build. Note: this prompt is long — if your Claude context window is limited, use Option B instead.
- **Option B (recommended):** Use Prompts 1 → 2 → 3 → 4 in sequence. Each builds on the previous. Test each phase before starting the next.

---
---

# PROMPT 0 — CONSOLIDATED (Full Build)

---

## System Role

You are a Senior Protocol Engineer specializing in Decentralized Autonomous Agents and the Sovereign Tech Stack. You write production-grade async Python and modern React/Three.js. Every function contains real logic — no `pass`, no `# TODO`, no `raise NotImplementedError`, no mock returns.

## What You Are Building

**MYKO** — a local-first, decentralized Life OS where a locally-running AI agent is the sole executor of every action.

### The Architecture

1. **The Brain:** Goose — a local LLM agent running on the user's machine. It communicates with MYKO exclusively through the Model Context Protocol (MCP). Goose decides what to store, what to broadcast, and what to pay. It is the only entry point for all system actions.

2. **The Nervous System:** A Python MCP Server that exposes MYKO's capabilities as callable tools over stdio transport. Goose connects to this server. The server handles tool discovery (`tools/list`), tool invocation (`tools/call`), and returns structured results. This is the backbone — without it, nothing else functions.

3. **The Memory:** An encrypted vault backed by IPFS. All data is AES-256-GCM encrypted locally before it ever touches the network. Encrypted blobs are pinned to a local Kubo (IPFS) node and tracked in an encrypted manifest. Plaintext never leaves the machine.

4. **The Identity:** Nostr protocol integration. The user's secp256k1 keypair lives in the encrypted vault. Goose can sign NIP-01 events (including Proof-of-Work events) and broadcast them to relays — publishing reputation data or encrypted DMs (NIP-17 wrapping with NIP-44 encryption) without any central server.

5. **The Value Layer:** Bitcoin Lightning Network integration (LND or LNbits). Goose can check balances, create invoices, and pay invoices for external compute or agent-to-agent micropayments. Hard per-task and daily spend limits prevent wallet draining.

6. **The Interface:** A Tauri 2 desktop app with React 19 + Three.js. A spatial, glassmorphic dashboard that visualizes the live state of all five layers. Connects to the backend via a localhost-only FastAPI bridge.

### Core Principles

- No centralized Web2 APIs. No Google, no AWS, no Auth0. Everything is P2P, local-first, open-source.
- The user owns every private key. Goose acts as the executioner, never the owner.
- All encryption happens in-memory before any disk or network write.
- Every agent action is logged to a local audit trail.

### Process Architecture

The system runs as **two processes** managed by the Tauri desktop shell:

1. **MCP Server process** — `python -m backend.main` — spawned by Goose via stdio. Runs the MCP read loop. This is the agent-facing interface.
2. **Bridge Server process** — `python -m backend.bridge` — spawned by Tauri on app launch. Runs a FastAPI HTTP server on `127.0.0.1:9473`. This is the frontend-facing interface.

Both processes import the same backend modules (`crypto`, `storage`, `vault`, `nostr`, `lightning`) but run independently. The bridge does NOT proxy to the MCP server — it instantiates its own backend instances using the same config and shared encrypted manifest on disk. The manifest file uses OS-level file locking (`fcntl.flock`) to prevent corruption from concurrent writes.

```
┌─────────────────────────────────────────────────┐
│                   User's Machine                │
│                                                 │
│  ┌──────────┐    stdio     ┌──────────────────┐ │
│  │  Goose   │◄────────────►│  MCP Server      │ │
│  │  (LLM)   │              │  (backend.main)  │ │
│  └──────────┘              └────────┬─────────┘ │
│                                     │ imports    │
│  ┌──────────┐    HTTP      ┌───────┴──────────┐ │
│  │  Tauri   │◄────────────►│  Bridge Server   │ │
│  │  (UI)    │  :9473       │  (backend.bridge) │ │
│  └──────────┘              └────────┬─────────┘ │
│                                     │ imports    │
│                             ┌───────┴──────────┐ │
│                             │  Shared Backend  │ │
│                             │  crypto, storage,│ │
│                             │  vault, nostr,   │ │
│                             │  lightning       │ │
│                             └────────┬─────────┘ │
│                                      │           │
│                    ┌─────────────────┼────────┐  │
│                    ▼                 ▼        ▼  │
│              ~/MYKO/            Kubo IPFS   LND/ │
│              manifest.enc       :5001       LNbits│
│              logs/                               │
└─────────────────────────────────────────────────┘
```

## File Structure

```
myko/
├── backend/
│   ├── __init__.py
│   ├── config.py              # Pydantic Settings v2, all config from .env
│   ├── crypto.py              # KeyManager: PBKDF2 derivation, AES-256-GCM, constant-time compare, memory wipe
│   ├── storage.py             # StorageEngine: aiohttp ↔ Kubo RPC, pin, fetch, retry logic
│   ├── vault.py               # VaultManager: encrypt-before-store, encrypted manifest with file locking
│   ├── nostr.py               # NostrClient: NIP-01 signing, NIP-17 DMs (NIP-44 encryption), PoW, multi-relay
│   ├── lightning.py           # LightningWallet: balance/invoice/pay, sat caps, drain protection
│   ├── mcp_server.py          # ★ MCP Server: stdio transport, JSON-RPC 2.0, tool registry, request dispatch
│   ├── mcp_tools.py           # Tool definitions: schemas, handlers, docstrings for Goose
│   ├── bridge.py              # FastAPI localhost-only HTTP server for Tauri frontend (separate process)
│   ├── logging_config.py      # Structured JSON audit logging, RotatingFileHandler
│   ├── main.py                # MCP entry point: boot server, register tools, start stdio loop
│   └── security.py            # Utility: secure_wipe(), constant_time_compare(), optional YubiKey challenge
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api/
│   │   │   └── bridge.ts             # Typed fetch wrapper with Bearer auth
│   │   ├── components/
│   │   │   ├── Layout.tsx
│   │   │   ├── Dashboard.tsx          # Main spatial overview with central 3D state orb
│   │   │   ├── StateOrb.tsx           # Three.js animated central orb
│   │   │   ├── GooseStatus.tsx        # ★ MCP brain heartbeat — primary panel
│   │   │   ├── VaultPanel.tsx
│   │   │   ├── VaultExplorer.tsx      # Force-directed 3D CID graph (route: /vault)
│   │   │   ├── IdentityPanel.tsx
│   │   │   ├── LightningPanel.tsx
│   │   │   ├── AuditFeed.tsx
│   │   │   └── GlassCard.tsx
│   │   ├── hooks/
│   │   │   ├── usePolling.ts
│   │   │   └── useSessionToken.ts
│   │   ├── types/
│   │   │   └── api.ts
│   │   └── styles/
│   │       └── globals.css
│   ├── src-tauri/
│   │   ├── tauri.conf.json
│   │   ├── Cargo.toml
│   │   └── src/main.rs              # Spawns bridge.py on launch, manages lifecycle
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── package.json
├── goose/
│   ├── goose_config.yaml          # Goose profile: stdio transport, env vars, working dir
│   └── sovereign_manifesto.md     # System prompt for Goose
├── requirements.txt               # Pinned versions
├── .env.example
└── README.md
```

## The Brain — MCP Server

### mcp_server.py — MCP Protocol Server (stdio transport)

This is the central nervous system. Goose launches it as a subprocess and communicates via stdin/stdout JSON-RPC 2.0.

**Protocol flow:**

```
Goose                          MYKO MCP Server
  │                                  │
  │──── initialize ─────────────────►│
  │◄─── {serverInfo, capabilities} ──│
  │                                  │
  │──── notifications/initialized ──►│  (no response)
  │                                  │
  │──── tools/list ─────────────────►│
  │◄─── [{name, description, inputSchema}, ...] │
  │                                  │
  │──── tools/call {name, args} ────►│
  │◄─── {content: [{type, text}]} ──│
  │                                  │
  │──── [repeat calls] ────────────►│
```

**Implementation requirements:**

- Read JSON-RPC 2.0 messages line-by-line from `stdin`, write responses to `stdout`, log to `stderr` only.
- Handle these MCP methods:
  - `initialize` → respond with `{"protocolVersion": "2024-11-05", "serverInfo": {"name": "myko", "version": "0.1.0"}, "capabilities": {"tools": {}}}`.
  - `notifications/initialized` → no response (notification, no `id`).
  - `tools/list` → return array of all registered tool schemas.
  - `tools/call` → look up tool by name, validate args, execute async handler, return `{"content": [{"type": "text", "text": "<JSON result>"}]}` on success or `{"content": [{"type": "text", "text": "Error: ..."}], "isError": true}` on failure.
- On startup: receive dependency-injected backend instances from `main.py`. No globals.
- Graceful shutdown on EOF/SIGTERM: close aiohttp sessions, flush logs, call `secure_wipe()` on any in-memory key material.
- All tool execution wrapped in try/except with structured MCP error responses.

**Do not use an external MCP SDK.** The server is ~200 lines of async stdin/stdout JSON-RPC. Write it directly.

```python
@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict  # JSON Schema
    handler: Callable[..., Awaitable[dict]]

class MCPServer:
    def __init__(self):
        self.tools: dict[str, Tool] = {}

    def register_tool(self, name: str, description: str, input_schema: dict, handler: Callable):
        ...

    async def handle_message(self, message: dict) -> dict | None:
        """Route JSON-RPC message. Return response dict, or None for notifications."""
        ...

    async def run(self):
        """Read stdin line-by-line, dispatch, write responses to stdout, flush."""
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin.buffer)
        ...
```

### main.py — MCP Entry Point

```
Usage: python -m backend.main
```

- Configure logging (stderr handler + audit file handler).
- Load config from `.env` via Pydantic Settings.
- Instantiate: `KeyManager(config)` → `StorageEngine(config)` → `VaultManager(key_mgr, storage)` → `NostrClient(vault, config)` → `LightningWallet.create(config)`.
- Instantiate `MCPServer()`.
- Register all 9 tools from `mcp_tools.py`, injecting backend instances via closures.
- `asyncio.run(server.run())`.

### goose/goose_config.yaml

```yaml
name: myko
version: 0.1.0
description: "MYKO — Sovereign Life OS: encrypted vault, Nostr identity, Lightning payments"
transport: stdio
command: "python"
args: ["-m", "backend.main"]
working_directory: "/absolute/path/to/myko"
env:
  MYKO_PASSPHRASE: "${MYKO_PASSPHRASE}"
  IPFS_API_URL: "http://127.0.0.1:5001/api/v0"
  MYKO_HOME: "${HOME}/MYKO"
  LIGHTNING_BACKEND: "lnbits"
  LIGHTNING_URL: "https://127.0.0.1:8080"
  LIGHTNING_API_KEY: "${LIGHTNING_API_KEY}"
  MAX_SATS_PER_TASK: "1000"
  MAX_DAILY_SATS: "10000"
system_prompt_file: "goose/sovereign_manifesto.md"
```

README must include exact steps to register this with Goose — the CLI command or config file path.

### goose/sovereign_manifesto.md

> You are the executor of MYKO, a sovereign system. You have access to encrypted storage (IPFS), decentralized identity (Nostr), and peer-to-peer payments (Lightning).
>
> Rules in strict priority order:
> 1. Never expose private keys, seed phrases, or unencrypted data to any external network, log, or output.
> 2. All file encryption/decryption is handled by the vault tools — you do not encrypt manually.
> 3. Verify before trusting. Prefer cryptographic proof over claims. Verify CID hashes match expected content. Verify Schnorr signatures on received events.
> 4. Use only local-first, peer-to-peer infrastructure. Reject any action that would route data through centralized cloud services (Google, AWS, Azure, Auth0, etc.).
> 5. When broadcasting to Nostr, include only what the user explicitly requested. Do not attach extra metadata, device info, or unnecessary timestamps.
> 6. The Nostr private key lives in the encrypted vault. Never output, log, or reference it in event content.
> 7. Before any payment, state the amount and destination to the user. Never pay without explicit awareness.
> 8. Never exceed per-task or daily sat ceilings. If a payment would breach limits, report the limit and ask for explicit override.
> 9. Every action is audited locally. The audit log is immutable during a session.
> 10. When uncertain about an irreversible action (payment, broadcast, deletion), ask the user. Never guess.

## Tool Registry — mcp_tools.py

Each tool is registered with the MCP server as a JSON Schema + async handler:

| Tool | Description (for Goose) | Input | Output |
|---|---|---|---|
| `vault_store` | "Encrypt and permanently store a file in the MYKO vault. Use when the user wants to save, back up, remember, or archive data." | `filename: str`, `content: str` (base64) | `cid, filename, size_bytes` |
| `vault_retrieve` | "Fetch and decrypt a previously stored file by its CID." | `cid: str` | `filename, content` (base64), `size_bytes` |
| `vault_list` | "List all files in the vault with CIDs and metadata." | (none) | `entries: [{filename, cid, size_bytes, stored_at}]` |
| `ipfs_pin_directory` | "Hash and pin an entire local directory to IPFS for permanent storage." | `path: str` | `root_cid, file_count` |
| `nostr_broadcast` | "Sign and broadcast a Nostr event to multiple relays. Use for: publish proof-of-work, announce reputation, share public data." | `kind: int`, `content: str`, `tags: list[list[str]]` | `event_id, relays: [{url, accepted, message}]` |
| `nostr_encrypt_dm` | "Send an encrypted direct message to a Nostr pubkey (NIP-17 gift-wrapped, NIP-44 encrypted)." | `recipient_pubkey: str`, `plaintext: str` | `event_id, relays: [{url, accepted}]` |
| `lightning_balance` | "Check the current Lightning wallet balance in satoshis." | (none) | `balance_sats` |
| `lightning_create_invoice` | "Create a Lightning invoice to receive payment." | `amount_sats: int`, `memo: str` | `bolt11, payment_hash` |
| `lightning_pay` | "Pay a Lightning invoice. Rejects if amount exceeds per-task or daily spend limits." | `bolt11: str` | `success, payment_hash, amount_sats, error` |

Each handler: `async def`, calls backend module, catches exceptions, returns JSON-serializable dict.

## The Memory — Crypto + Vault + IPFS

### security.py — Shared Security Utilities

- `secure_wipe(buffer: bytearray)`: overwrite buffer contents with zeros, then delete reference. Used everywhere sensitive data is handled.
- `constant_time_compare(a: bytes, b: bytes) → bool`: use `hmac.compare_digest`. Used in tag verification and token comparison.
- `yubikey_challenge(challenge: bytes) → bytes | None`: optional. If a YubiKey is detected via `ykman` CLI, send an HMAC-SHA256 challenge and return the response. Used to add a hardware factor to master key derivation (passphrase + YubiKey response = key material). If no YubiKey present, return `None` and fall back to passphrase-only derivation. Document this clearly in README.

### crypto.py — KeyManager

- Derive master key from `MYKO_PASSPHRASE` using `PBKDF2HMAC(SHA256, 600_000 iterations, 32-byte random salt)`.
- If `security.yubikey_challenge()` returns a response, concatenate `passphrase + yubikey_response` as the key material before PBKDF2. This adds hardware-bound security. If no YubiKey, passphrase alone is used.
- Ciphertext format: `salt(32) ‖ nonce(12) ‖ ciphertext ‖ tag(16)`.
- `encrypt(plaintext: bytes) → bytes`: fresh random salt + nonce per call.
- `decrypt(blob: bytes) → bytes`: parse components, derive key, decrypt.
- Use `cryptography.hazmat.primitives.ciphers.aead.AESGCM`.
- Derive key per call — never cache derived keys in memory.
- Call `secure_wipe()` on all intermediate key material and plaintext in `finally` blocks.
- Use `constant_time_compare()` implicitly via AESGCM (the library handles tag verification in constant time, but document this assumption).

### storage.py — StorageEngine

- Async class using `aiohttp.ClientSession`. Implements async context manager (`__aenter__`, `__aexit__`).
- Connect to Kubo RPC at config `IPFS_API_URL` (default `http://127.0.0.1:5001/api/v0`).
- `pin_file(data: bytes) → str`: POST multipart to `/add`, return CID `Hash` field.
- `pin_directory(path: str) → str`: POST `/add?recursive=true&wrap-with-directory=true`, return root CID.
- `fetch(cid: str) → bytes`: POST `/cat?arg={cid}`, return full body.
- Retry: exponential backoff (1s, 2s, 4s), max 3 attempts, 30s timeout per request.
- Typed `StorageError(Exception)` with context message on all failures.

### vault.py — VaultManager

- Composes `KeyManager` + `StorageEngine`.
- On init, load encrypted manifest from `~/MYKO/manifest.enc` (or create empty). Use `fcntl.flock(LOCK_EX)` during reads and writes to prevent corruption when MCP server and bridge access it concurrently.
- `store(filename, content) → ManifestEntry`: encrypt content → pin encrypted blob → add entry to manifest → flush manifest (acquire lock, write, release).
- `retrieve(cid) → bytes`: fetch from IPFS → decrypt → return. Wipe plaintext after caller is done (document that callers must handle this).
- `list() → list[ManifestEntry]`.
- `ManifestEntry` (Pydantic v2 model): `filename: str`, `cid: str`, `size_bytes: int`, `stored_at: datetime`.
- Manifest itself is AES-256-GCM encrypted with the same KeyManager before writing to disk.

## The Identity — Nostr

### nostr.py — NostrClient

- On first use, generate secp256k1 keypair. Store privkey bytes in vault via `vault.store("nostr_privkey", privkey_bytes)`. On subsequent loads, retrieve from vault by looking up the CID in the manifest.
- `get_pubkey() → str`: hex-encoded compressed public key.
- `create_event(kind: int, content: str, tags: list[list[str]], pow_target: int | None = None) → SignedEvent`:
  - Build unsigned event with current unix timestamp.
  - If `pow_target` is set, iterate nonce in tags until event ID has `pow_target` leading zero bits (NIP-13 Proof of Work).
  - Compute event ID: SHA-256 of NIP-01 serialized JSON array `[0, pubkey, created_at, kind, tags, content]`.
  - Sign the 32-byte event ID with Schnorr (BIP-340) using the private key.
  - Return `SignedEvent`.
- `broadcast(event: SignedEvent, relays: list[str] | None = None) → list[RelayResponse]`:
  - Default to config `NOSTR_RELAYS` if none provided.
  - For each relay, open WebSocket via `websockets`, send `["EVENT", event_dict]`, await `["OK", event_id, success, message]` with 10s timeout.
  - Skip failed relays gracefully — log error, continue to next.
  - Return list of `RelayResponse`.
- `send_dm(recipient_pubkey: str, plaintext: str) → tuple[str, list[RelayResponse]]`:
  - Encrypt plaintext using NIP-44 (versioned symmetric encryption with ECDH + HKDF conversation key derived from sender privkey + recipient pubkey).
  - Wrap in NIP-17 gift-wrap: create a kind:14 rumor (unsigned), seal it in a kind:13 seal (signed, encrypted to recipient), wrap in a kind:1059 gift-wrap (signed with random throwaway key, encrypted to recipient).
  - Broadcast the kind:1059 event.
  - Return `(event_id, relay_responses)`.
- Use `coincurve` for secp256k1 curve operations. Use `websockets` for relay connections.

### Pydantic Models (in nostr.py or separate models.py)

- `UnsignedEvent`: `pubkey`, `created_at`, `kind`, `tags`, `content`. Method `serialize() → str` producing NIP-01 JSON array.
- `SignedEvent`: extends with `id`, `sig`. Method `to_dict()` for relay transmission.
- `RelayResponse`: `relay_url`, `accepted`, `message`.

## The Value Layer — Lightning

### lightning.py — LightningWallet

- Abstract base class with two implementations: `LNDWallet` and `LNbitsWallet`. Factory classmethod `LightningWallet.create(config) → LightningWallet` selects based on `LIGHTNING_BACKEND`.
- **LNDWallet:** REST API at `LIGHTNING_URL`. Auth via macaroon file (read from `LIGHTNING_MACAROON_PATH`, sent as `Grpc-Metadata-macaroon` hex header). TLS cert verification from `LIGHTNING_TLS_CERT_PATH`.
- **LNbitsWallet:** REST API at `LIGHTNING_URL/api/v1/`. Auth via `X-Api-Key` header from `LIGHTNING_API_KEY`.
- Shared interface:
  - `get_balance() → int`: confirmed balance in sats.
  - `create_invoice(amount_sats: int, memo: str) → str`: return BOLT11 invoice string.
  - `pay_invoice(bolt11: str) → PaymentResult`: decode invoice amount first (use `bolt11` library or manual parsing of the amount field). REJECT if:
    - Amount > `MAX_SATS_PER_TASK` (default 1000 sats).
    - Rolling 24h cumulative spend + this amount > `MAX_DAILY_SATS` (default 10000 sats).
  - `PaymentResult` (Pydantic v2): `success: bool`, `payment_hash: str | None`, `error: str | None`, `amount_sats: int`.
- In-memory spend tracker: `list[tuple[float, int]]` of `(unix_timestamp, amount_sats)`. Prune entries older than 24h on each `pay_invoice` call.
- Never log payment preimages. Log payment hashes only.

## The Interface — Frontend

### bridge.py — Tauri ↔ Python IPC (separate process)

```
Usage: python -m backend.bridge
```

- FastAPI bound to `127.0.0.1:9473` (never `0.0.0.0`).
- On launch: generate random 64-char hex token → write to `~/MYKO/.session_token` (mode `0600`). Tauri reads it on startup.
- All requests require `Authorization: Bearer <token>`. Use `constant_time_compare()` for token validation.
- CORS: allow origin `tauri://localhost` only.
- Instantiates its own `KeyManager`, `StorageEngine`, `VaultManager`, `NostrClient`, `LightningWallet` from the same config — sharing the same encrypted manifest on disk (file-locked).
- Endpoints:
  - `GET /vault/list` → `{entries: [ManifestEntry]}`
  - `POST /vault/store` → `{filename, content (base64)}` → `{cid, filename, size_bytes}`
  - `POST /vault/retrieve` → `{cid}` → `{filename, content (base64)}`
  - `GET /lightning/balance` → `{balance_sats}`
  - `GET /identity/info` → `{npub, relays: [{url, connected}], last_broadcast}`
  - `GET /audit/recent?limit=50` → `{entries: [{ts, action, tool, ok, error}]}`
  - `GET /goose/status` → `{mcp_pid: int | null, uptime_seconds, last_tool_call, total_calls}` — reads a shared status file (`~/MYKO/.goose_status.json`) that the MCP server writes on each tool call.
- The MCP server writes `~/MYKO/.goose_status.json` (updated on every tool call): `{pid, started_at, last_tool, last_tool_ts, total_calls}`. Bridge reads this file for the `/goose/status` endpoint.

### Visual Design System

| Token | Value |
|---|---|
| Background | `#000000` |
| GlassCard fill | `rgba(255,255,255,0.03)` |
| GlassCard border | `1px solid rgba(255,255,255,0.08)` |
| GlassCard blur | `backdrop-filter: blur(20px)` |
| GlassCard radius | `16px` |
| Primary text | `#FFFFFF` |
| Muted text | `rgba(255,255,255,0.5)` |
| Data font | `JetBrains Mono, monospace` |
| UI font | `Inter, system-ui, sans-serif` |
| Vault/IPFS | `#00F0FF` (cyan) |
| Nostr/Identity | `#A855F7` (purple) |
| Lightning | `#F59E0B` (amber) |
| Goose/MCP | `#3B82F6` (blue) |
| Healthy | `#22C55E` (green) |
| Error | `#EF4444` (red) |

### Three.js Scene

- Full-viewport `<Canvas>` with `#000` clear color and subtle volumetric fog shader.
- Central orb: sphere with animated simplex noise vertex displacement via `useFrame`. Color reflects system state: slow cyan pulse = healthy, amber = warning (relay disconnections or high spend), red = error (IPFS/Lightning unreachable), gray = Goose disconnected.
- Glassmorphic HTML panels positioned around the orb.

### Dashboard Components

- **GooseStatus.tsx ★ (top-center):** The brain's heartbeat. Blue pulse animation when Goose/MCP connected, gray when disconnected. Shows: uptime, last tool call name + timestamp, total calls this session. Polls `GET /goose/status` every 2s. Accent: blue.
- **VaultPanel.tsx (top-left):** File count, total pinned size, last action filename + timestamp. Accent: cyan. Link to `/vault` explorer.
- **IdentityPanel.tsx (top-right):** Nostr npub (truncated center, click to copy full), relay status dots (green = connected, gray = disconnected per relay), last broadcast event kind + timestamp. Accent: purple.
- **LightningPanel.tsx (bottom-left):** Balance in sats (large number), daily spend as progress bar against `MAX_DAILY_SATS`, last payment amount + timestamp. Accent: amber.
- **AuditFeed.tsx (bottom-right):** Scrollable list, max 50 entries. Each: timestamp, action name, tool badge (colored by tool category), success/fail indicator. Auto-scroll to newest.
- **VaultExplorer.tsx (route `/vault`):** Force-directed 3D graph via Three.js. Nodes = CIDs from manifest. Node color: cyan. Node size: proportional to `size_bytes`. Click node → slide-in detail panel: filename, full CID (copyable), size, `stored_at`, retrieve button.
- **GlassCard.tsx:** Reusable container applying all glass tokens. Props: `children`, `className`, `accentColor` (optional top-border glow).
- **Dashboard.tsx:** CSS Grid layout. Orb fills ~40% of viewport center. Five GlassCard panels arranged around it. Each fetches data via `usePolling(endpoint, 2000)`. On fetch failure, display last-known data with a muted "stale" indicator.

### Frontend Infrastructure

- **bridge.ts:** `API_BASE = "http://127.0.0.1:9473"`. Read session token from `~/MYKO/.session_token` via Tauri `fs` API. `async function apiFetch<T>(path, options?): Promise<T>` attaching Bearer auth. Cache last successful response per endpoint; return cached on network failure.
- **usePolling.ts:** Generic hook. `usePolling<T>(path: string, intervalMs: number) → { data: T | null, stale: boolean, error: string | null }`.
- **useSessionToken.ts:** Read token once on mount via Tauri fs, store in ref.
- **types/api.ts:** TypeScript interfaces matching all backend Pydantic models.

### Tauri Configuration

- App name: `MYKO`. Window: minimal chrome, `1280x800` default, dark background.
- `src-tauri/src/main.rs`: on app launch, spawn `python -m backend.bridge` as a sidecar process. On app close, send SIGTERM to the bridge process.
- Permissions: filesystem read access (for `~/MYKO/.session_token`), localhost HTTP allowed.
- CSP: no external URLs allowed. All assets bundled locally.
- No analytics, no telemetry, no CDN, no external fonts (bundle Inter and JetBrains Mono).

## Config & Infrastructure

### config.py — Pydantic Settings v2

All from `.env`, all typed:

- `MYKO_PASSPHRASE: str`
- `MYKO_HOME: Path` (default `~/MYKO`)
- `IPFS_API_URL: str` (default `http://127.0.0.1:5001/api/v0`)
- `NOSTR_RELAYS: list[str]` (default `["wss://relay.damus.io", "wss://nos.lol", "wss://relay.nostr.band"]`)
- `NOSTR_KEY_FILENAME: str` (default `"nostr_privkey"`)
- `LIGHTNING_BACKEND: Literal["lnd", "lnbits"]` (default `"lnbits"`)
- `LIGHTNING_URL: str`
- `LIGHTNING_MACAROON_PATH: Path | None` (default `None`)
- `LIGHTNING_API_KEY: str | None` (default `None`)
- `LIGHTNING_TLS_CERT_PATH: Path | None` (default `None`)
- `MAX_SATS_PER_TASK: int` (default `1000`)
- `MAX_DAILY_SATS: int` (default `10000`)
- `LOG_LEVEL: str` (default `"INFO"`)
- `BRIDGE_PORT: int` (default `9473`)
- `YUBIKEY_ENABLED: bool` (default `False`)

### logging_config.py

- `RotatingFileHandler` → `~/MYKO/logs/audit.jsonl`, 10 MB max, 5 backups.
- JSON entries: `{"ts": ISO8601, "action": str, "tool": str, "input_hash": SHA256, "output_hash": SHA256, "ok": bool, "error": str | null}`.
- Never log keys, plaintext, passphrases, preimages, or macaroons. SHA-256 hashes of inputs/outputs only.
- Stderr handler for real-time debug output (MCP server uses this since stdout is reserved for JSON-RPC).

### .env.example

```env
# === REQUIRED ===
MYKO_PASSPHRASE=your-strong-passphrase-here

# === STORAGE ===
MYKO_HOME=~/MYKO
IPFS_API_URL=http://127.0.0.1:5001/api/v0

# === IDENTITY ===
NOSTR_RELAYS=["wss://relay.damus.io","wss://nos.lol","wss://relay.nostr.band"]

# === PAYMENTS ===
LIGHTNING_BACKEND=lnbits
LIGHTNING_URL=https://127.0.0.1:8080
LIGHTNING_API_KEY=your-lnbits-api-key
# For LND instead:
# LIGHTNING_BACKEND=lnd
# LIGHTNING_MACAROON_PATH=/path/to/admin.macaroon
# LIGHTNING_TLS_CERT_PATH=/path/to/tls.cert

# === LIMITS ===
MAX_SATS_PER_TASK=1000
MAX_DAILY_SATS=10000

# === SECURITY ===
YUBIKEY_ENABLED=false
LOG_LEVEL=INFO
BRIDGE_PORT=9473
```

### Security Hardening Notes (include in README)

1. **Hardware key (YubiKey):** When `YUBIKEY_ENABLED=true`, master key derivation incorporates a YubiKey HMAC-SHA256 challenge-response. This means the vault cannot be decrypted without both the passphrase AND physical possession of the YubiKey. Requires `ykman` CLI installed.
2. **Memory wiping:** All sensitive byte arrays (keys, plaintext, passphrases) are overwritten with zeros via `secure_wipe()` in `finally` blocks. This reduces the window for memory dumping attacks but is not a guarantee in Python due to the garbage collector potentially copying objects. Document this limitation.
3. **Constant-time operations:** Token comparison in the bridge and HMAC verification use `hmac.compare_digest()` to prevent timing side-channels.
4. **Process sandboxing (recommended, not enforced):** Document that users can run the MCP server and bridge under a dedicated OS user with restricted filesystem access, or use `firejail`/`bubblewrap` on Linux to sandbox the processes. The README should include example commands.
5. **No secrets in logs:** Enforced at the logging layer. Audit entries only contain SHA-256 hashes of inputs/outputs, never raw content.
6. **File permissions:** `.session_token` written with `0600`. `manifest.enc` written with `0600`. `.env` should be `0600`.

### README.md

Must include:
1. What MYKO is (one paragraph).
2. Prerequisites: Python 3.12+, Node 20+, Rust/Cargo (for Tauri), running Kubo (IPFS) node, LND or LNbits instance, Goose installed. Optional: YubiKey + `ykman`.
3. Install backend: `pip install -r requirements.txt`.
4. Install frontend: `cd frontend && npm install`.
5. Configure: `cp .env.example .env` and fill in values.
6. Register with Goose: exact command to add the MYKO toolkit (e.g., `goose toolkit add ./goose/goose_config.yaml` — verify against current Goose docs).
7. Launch: (a) Start Kubo: `ipfs daemon`. (b) Start Lightning node. (c) Start bridge: `python -m backend.bridge`. (d) Start Tauri app: `cd frontend && npm run tauri dev`. (e) In Goose, the MCP server starts automatically when Goose invokes a MYKO tool.
8. Verify: open Goose, ask "store a test file in the vault", then "list the vault", then "retrieve the file".
9. Security hardening section with sandboxing examples.

## Output Instructions

1. Print the full folder tree.
2. For every file: full path as header, then complete file contents.
3. No `pass`, no `# TODO`, no stubs. Every function has real implementation.
4. Pin all dependency versions in `requirements.txt` and `package.json`.
5. `.env.example` with all variables documented.
6. `README.md` as specified above.
7. Use Pydantic v2 (`model_validator`, `ConfigDict`) throughout — not v1 syntax.


---
---

# PROMPT 1 — PHASE 1: The Brain + The Memory

> Start here. Builds the MCP server and encrypted vault. Test with Goose before moving on.

---

## System Role

You are a Senior Protocol Engineer specializing in the Model Context Protocol and local-first encrypted systems. You write production-grade async Python 3.12+. Every function contains real logic — no stubs, no placeholders.

## What You Are Building

The foundation of **MYKO**: the MCP server that Goose connects to (the brain's interface) and the encrypted storage layer it exposes (the memory).

After this phase, Goose can:
- Connect to MYKO via stdio MCP transport
- Discover tools via `tools/list`
- Store an encrypted file to IPFS (`vault_store`)
- List stored files (`vault_list`)
- Retrieve and decrypt a file (`vault_retrieve`)
- Pin a local directory (`ipfs_pin_directory`)

## File Structure

```
myko/
├── backend/
│   ├── __init__.py
│   ├── config.py
│   ├── security.py            # secure_wipe, constant_time_compare, optional yubikey_challenge
│   ├── crypto.py
│   ├── storage.py
│   ├── vault.py
│   ├── mcp_server.py          # ★ MCP Protocol Server
│   ├── mcp_tools.py           # Vault tools only (4 tools)
│   ├── logging_config.py
│   └── main.py
├── goose/
│   ├── goose_config.yaml
│   └── sovereign_manifesto.md
├── tests/
│   ├── test_crypto.py
│   ├── test_storage.py
│   ├── test_vault.py
│   └── test_mcp_server.py
├── requirements.txt
├── .env.example
└── README.md
```

## Specifications

### mcp_server.py — MCP Protocol Server (stdio)

Most important file. Goose spawns `python -m backend.main` as subprocess. Communication over stdin (JSON-RPC in) / stdout (JSON-RPC out). All logging to stderr only.

**Handlers:**

1. `initialize` → respond with `{"protocolVersion": "2024-11-05", "serverInfo": {"name": "myko", "version": "0.1.0"}, "capabilities": {"tools": {}}}`.
2. `notifications/initialized` → no response.
3. `tools/list` → return all registered tool schemas.
4. `tools/call` → dispatch to handler, return `{"content": [{"type": "text", "text": "<JSON>"}]}` or `{"content": [...], "isError": true}`.

Requests have `id` (need response). Notifications have no `id` (no response). Implement directly — no external MCP SDK.

```python
@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    handler: Callable[..., Awaitable[dict]]

class MCPServer:
    def __init__(self):
        self.tools: dict[str, Tool] = {}

    def register_tool(self, name, description, input_schema, handler): ...
    async def handle_message(self, msg: dict) -> dict | None: ...
    async def run(self): ...  # stdin read loop
```

On shutdown (EOF/SIGTERM): close sessions, flush logs, `secure_wipe()` key material. Write status to `~/MYKO/.goose_status.json` on every tool call: `{pid, started_at, last_tool, last_tool_ts, total_calls}`.

### main.py

- Configure logging (stderr + audit file).
- Load config. Instantiate `KeyManager` → `StorageEngine` → `VaultManager`.
- Create `MCPServer`, register 4 vault tools via closures.
- `asyncio.run(server.run())`.

### goose/goose_config.yaml

```yaml
name: myko
description: "MYKO Sovereign Life OS — encrypted vault, decentralized storage"
transport: stdio
command: "python"
args: ["-m", "backend.main"]
working_directory: "/absolute/path/to/myko"
env:
  MYKO_PASSPHRASE: "${MYKO_PASSPHRASE}"
  IPFS_API_URL: "http://127.0.0.1:5001/api/v0"
  MYKO_HOME: "${HOME}/MYKO"
  YUBIKEY_ENABLED: "false"
```

### goose/sovereign_manifesto.md

> You are the executor of MYKO, a sovereign system with encrypted permanent storage.
> 1. Never expose unencrypted data to any external network or log.
> 2. Vault tools handle all encryption — do not encrypt manually.
> 3. Use descriptive filenames so the user can find files later.
> 4. Present vault listings clearly with filenames and CIDs.
> 5. Every action is logged to the local audit trail.
> 6. Reject any request that would route data through centralized cloud services.

### mcp_tools.py — 4 Vault Tools

**vault_store**: "Encrypt and permanently store a file. Use for: save, back up, remember, archive." Input: `filename: str`, `content: str` (base64). Handler: decode → `vault.store()` → return `{cid, filename, size_bytes}`.

**vault_retrieve**: "Fetch and decrypt a stored file by CID." Input: `cid: str`. Handler: `vault.retrieve()` → encode → return `{filename, content, size_bytes}`.

**vault_list**: "List all files in the vault." Input: none. Handler: `vault.list()` → return `{entries}`.

**ipfs_pin_directory**: "Pin an entire local directory to IPFS." Input: `path: str`. Handler: `storage.pin_directory()` → return `{root_cid}`.

### security.py

- `secure_wipe(buf: bytearray)`: zero-fill, delete ref.
- `constant_time_compare(a, b) → bool`: `hmac.compare_digest`.
- `yubikey_challenge(challenge: bytes) → bytes | None`: if `YUBIKEY_ENABLED` and `ykman` available, HMAC-SHA256 challenge-response. Else `None`.

### crypto.py — KeyManager

- `PBKDF2HMAC(SHA256, 600_000 iters, 32-byte salt)` from passphrase (+ YubiKey response if enabled).
- `encrypt(plaintext) → salt(32) ‖ nonce(12) ‖ ciphertext ‖ tag(16)`.
- `decrypt(blob) → plaintext`.
- `AESGCM` from `cryptography.hazmat`. Derive per call. `secure_wipe()` in `finally`.

### storage.py — StorageEngine

- Async `aiohttp.ClientSession`. Context manager.
- `pin_file(data) → CID`, `pin_directory(path) → CID`, `fetch(cid) → bytes`.
- Exponential backoff (1s, 2s, 4s), 3 retries, 30s timeout. `StorageError`.

### vault.py — VaultManager

- `KeyManager` + `StorageEngine`.
- `store(filename, content) → ManifestEntry`. `retrieve(cid) → bytes`. `list() → list[ManifestEntry]`.
- Manifest at `~/MYKO/manifest.enc`, encrypted, file-locked (`fcntl.flock`).
- `ManifestEntry` (Pydantic v2): `filename`, `cid`, `size_bytes`, `stored_at`.

### config.py

Pydantic Settings v2: `MYKO_PASSPHRASE`, `IPFS_API_URL`, `MYKO_HOME`, `LOG_LEVEL`, `YUBIKEY_ENABLED`.

### logging_config.py

`RotatingFileHandler` → `~/MYKO/logs/audit.jsonl`, 10 MB, 5 backups. JSON. Never log secrets.

### tests/

- `test_crypto.py`: roundtrip, wrong passphrase fails, unique salts per call.
- `test_storage.py`: mock Kubo, test pin/fetch/retry/timeout.
- `test_vault.py`: store → list → retrieve cycle with mocked IPFS.
- `test_mcp_server.py`: simulate `initialize` → `tools/list` → `tools/call` flow. Verify JSON-RPC format. Unknown method → error. Bad args → error. Notification → no response.

## Output

1. Full folder tree. 2. Every file: path + complete contents. 3. Pinned `requirements.txt`. 4. `.env.example`. 5. `README.md`: prerequisites, install, register with Goose (exact command), run tests, verify via Goose.


---
---

# PROMPT 2 — PHASE 2: The Identity (Nostr)

> Use after Phase 1 works and Goose calls vault tools. Do not recreate existing modules — import and extend.

---

## System Role

You are a Senior Protocol Engineer adding Nostr identity to MYKO's existing MCP server.

## What You Are Adding

`NostrClient` + 2 new MCP tools. After this, Goose can also sign/broadcast NIP-01 events (including Proof-of-Work) and send NIP-17 gift-wrapped encrypted DMs.

## New/Modified Files

```
myko/
├── backend/
│   ├── nostr.py             # NEW
│   ├── models.py            # NEW — Nostr Pydantic v2 models
│   ├── mcp_tools.py         # MODIFIED — add 2 tools
│   ├── config.py            # MODIFIED — add NOSTR_RELAYS, NOSTR_KEY_FILENAME
│   └── main.py              # MODIFIED — instantiate NostrClient, register tools
├── goose/
│   └── sovereign_manifesto.md  # MODIFIED — add rules 7-8
├── tests/
│   └── test_nostr.py        # NEW
└── requirements.txt         # MODIFIED — add coincurve, websockets
```

## Specifications

### config.py additions
- `NOSTR_RELAYS: list[str]` (default `["wss://relay.damus.io", "wss://nos.lol", "wss://relay.nostr.band"]`)
- `NOSTR_KEY_FILENAME: str` (default `"nostr_privkey"`)

### models.py (Pydantic v2)
- `UnsignedEvent`: `pubkey`, `created_at`, `kind`, `tags`, `content`. `serialize() → str` per NIP-01.
- `SignedEvent`: adds `id`, `sig`. `to_dict() → dict`.
- `RelayResponse`: `relay_url`, `accepted`, `message`.

### nostr.py — NostrClient
- **Key management:** first use → generate secp256k1 keypair → `vault.store("nostr_privkey", privkey_bytes)`. Subsequent → retrieve from vault manifest.
- `get_pubkey() → str`: hex.
- `create_event(kind, content, tags, pow_target=None) → SignedEvent`:
  - If `pow_target` set: iterate nonce tag until event ID has required leading zero bits (NIP-13).
  - NIP-01 serialize → SHA-256 → Schnorr sign (BIP-340).
- `broadcast(event, relays=None) → list[RelayResponse]`: WebSocket per relay, `["EVENT", ...]`, await `["OK", ...]`, 10s timeout, skip failures.
- `send_dm(recipient_pubkey, plaintext) → (event_id, list[RelayResponse])`:
  - NIP-44 encryption (ECDH + HKDF conversation key).
  - NIP-17 gift-wrap: kind:14 rumor → kind:13 seal (signed, encrypted to recipient) → kind:1059 gift-wrap (random throwaway key, encrypted to recipient).
  - Broadcast the kind:1059.
- Use `coincurve` + `websockets`.

### mcp_tools.py additions

**nostr_broadcast**: "Sign and broadcast a Nostr event. Use for: publish proof-of-work, announce reputation, share public data." Input: `kind: int`, `content: str`, `tags: list[list[str]]`, `pow_target: int | null`. Handler: create → broadcast → return `{event_id, relays}`.

**nostr_encrypt_dm**: "Send an encrypted DM to a Nostr pubkey (NIP-17 gift-wrapped, NIP-44 encrypted)." Input: `recipient_pubkey: str`, `plaintext: str`. Handler: `send_dm()` → return `{event_id, relays}`.

### main.py: instantiate `NostrClient(vault, config)`, register 2 tools. Server now has 6 tools.

### sovereign_manifesto.md additions
> 7. When broadcasting to Nostr, include only what the user explicitly requested. No extra metadata.
> 8. The Nostr private key lives in the vault. Never output, log, or reference it in content.

### tests/test_nostr.py
- NIP-01 serialization. Sign/verify roundtrip. NIP-13 PoW (verify leading zeros). Mock WebSocket broadcast. NIP-44 encrypt/decrypt between two keypairs. NIP-17 gift-wrap structure validation.

## Output
1. New and modified files only. 2. Updated tree. 3. Full contents. 4. Updated `requirements.txt`.


---
---

# PROMPT 3 — PHASE 3: The Value Layer (Lightning) + Final Tool Registry

> Use after Phase 2. Assumes MCP server with 6 tools is working.

---

## System Role

You are a Senior Protocol Engineer adding Bitcoin Lightning payments to MYKO. Import existing modules — do not recreate.

## What You Are Adding

1. `LightningWallet` with spend protection.
2. 3 new MCP tools. Server reaches full complement of 9 tools.
3. Finalized Goose config and manifesto.

## New/Modified Files

```
myko/
├── backend/
│   ├── lightning.py          # NEW
│   ├── mcp_tools.py          # MODIFIED — add 3 tools
│   ├── config.py             # MODIFIED — add Lightning config
│   └── main.py               # MODIFIED — instantiate wallet, register tools
├── goose/
│   ├── goose_config.yaml     # MODIFIED — final with all env vars
│   └── sovereign_manifesto.md # MODIFIED — final 10 rules
├── tests/
│   ├── test_lightning.py     # NEW
│   └── test_mcp_tools.py     # NEW — all 9 tools integration test
└── requirements.txt          # MODIFIED
```

## Specifications

### config.py additions
`LIGHTNING_BACKEND: Literal["lnd", "lnbits"]`, `LIGHTNING_URL`, `LIGHTNING_MACAROON_PATH`, `LIGHTNING_API_KEY`, `LIGHTNING_TLS_CERT_PATH`, `MAX_SATS_PER_TASK` (1000), `MAX_DAILY_SATS` (10000).

### lightning.py
- Abstract base → `LNDWallet` (REST + macaroon + TLS) + `LNbitsWallet` (REST + API key). Factory `LightningWallet.create(config)`.
- `get_balance() → int`. `create_invoice(amount_sats, memo) → str`. `pay_invoice(bolt11) → PaymentResult`.
- Reject: amount > per-task cap OR rolling 24h + amount > daily cap.
- `PaymentResult` (Pydantic v2): `success`, `payment_hash`, `error`, `amount_sats`.
- In-memory spend list, prune >24h. Never log preimages.

### mcp_tools.py additions

**lightning_balance**: "Check Lightning balance in sats." → `{balance_sats}`.
**lightning_create_invoice**: "Create invoice to receive payment." Input: `amount_sats`, `memo`. → `{bolt11, payment_hash}`.
**lightning_pay**: "Pay a Lightning invoice. Rejects over per-task or daily limits." Input: `bolt11`. → `PaymentResult`.

### main.py: instantiate wallet, register 3 tools. Server: 9 tools total.

### goose_config.yaml — Final

```yaml
name: myko
version: 0.1.0
description: "MYKO — Sovereign Life OS: encrypted vault, Nostr identity, Lightning payments"
transport: stdio
command: "python"
args: ["-m", "backend.main"]
working_directory: "/absolute/path/to/myko"
env:
  MYKO_PASSPHRASE: "${MYKO_PASSPHRASE}"
  IPFS_API_URL: "http://127.0.0.1:5001/api/v0"
  MYKO_HOME: "${HOME}/MYKO"
  LIGHTNING_BACKEND: "lnbits"
  LIGHTNING_URL: "https://127.0.0.1:8080"
  LIGHTNING_API_KEY: "${LIGHTNING_API_KEY}"
  MAX_SATS_PER_TASK: "1000"
  MAX_DAILY_SATS: "10000"
  YUBIKEY_ENABLED: "false"
system_prompt_file: "goose/sovereign_manifesto.md"
```

### sovereign_manifesto.md — Final (10 rules)

> You are the executor of MYKO, a sovereign system. You have access to encrypted storage (IPFS), decentralized identity (Nostr), and peer-to-peer payments (Lightning).
>
> 1. Never expose private keys, seed phrases, or unencrypted data to any external network, log, or output.
> 2. Vault tools handle all encryption — do not encrypt manually.
> 3. Verify before trusting. Prefer cryptographic proof over claims.
> 4. Local-first only. Reject any action routing through centralized cloud services.
> 5. Nostr broadcasts: include only what the user explicitly requested. No extra metadata.
> 6. Nostr private key stays in the vault. Never output, log, or reference it.
> 7. Before any payment, state the amount and destination. Never pay silently.
> 8. Never exceed per-task or daily sat limits. Ask for override if needed.
> 9. Every action is audited locally.
> 10. When uncertain about irreversible actions, ask the user. Never guess.

### tests/
- `test_lightning.py`: spend limit enforcement (per-task, daily, rolling window), mock both LND and LNbits responses, test factory selection.
- `test_mcp_tools.py`: simulate full MCP flow for all 9 tools with mocked backends. Verify each tool's schema is valid JSON Schema. Verify error responses for bad inputs. Verify all tools return JSON-serializable results.

## Output
1. New/modified files only. 2. Updated tree. 3. Full contents. 4. Updated `requirements.txt`.


---
---

# PROMPT 4 — PHASE 4: The Interface (Tauri + React + Three.js)

> Use after Phases 1-3 work and Goose calls all 9 tools successfully.

---

## System Role

You are a Senior Frontend Engineer building a Tauri 2 desktop application with React 19 and Three.js. TypeScript strict mode. Every component is functional with real data-fetching.

## What You Are Building

The **MYKO Dashboard** — a spatial desktop interface visualizing all five system layers. Plus the `bridge.py` backend it connects to.

## File Structure

```
myko/
├── backend/
│   └── bridge.py                   # NEW — FastAPI IPC server (separate process)
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api/
│   │   │   └── bridge.ts
│   │   ├── components/
│   │   │   ├── Layout.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   ├── StateOrb.tsx
│   │   │   ├── GooseStatus.tsx     # ★ Brain heartbeat
│   │   │   ├── VaultPanel.tsx
│   │   │   ├── VaultExplorer.tsx   # Route: /vault
│   │   │   ├── IdentityPanel.tsx
│   │   │   ├── LightningPanel.tsx
│   │   │   ├── AuditFeed.tsx
│   │   │   └── GlassCard.tsx
│   │   ├── hooks/
│   │   │   ├── usePolling.ts
│   │   │   └── useSessionToken.ts
│   │   ├── types/
│   │   │   └── api.ts
│   │   └── styles/
│   │       └── globals.css
│   ├── src-tauri/
│   │   ├── tauri.conf.json
│   │   ├── Cargo.toml
│   │   └── src/main.rs            # Spawns bridge.py, manages lifecycle
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── package.json
```

## bridge.py — Backend HTTP Server (separate process)

```
Usage: python -m backend.bridge
```

- FastAPI on `127.0.0.1:9473` (never `0.0.0.0`).
- On launch: generate random 64-char hex token → `~/MYKO/.session_token` (file mode `0600`). Use `constant_time_compare()` for token validation on every request.
- CORS: `tauri://localhost` only.
- Instantiates its own backend module instances from same config. Shares `manifest.enc` on disk with MCP server via file locking.
- Reads `~/MYKO/.goose_status.json` (written by MCP server) for Goose status.
- Endpoints:
  - `GET /vault/list` → `{entries: [ManifestEntry]}`
  - `POST /vault/store` → `{filename, content}` → `{cid, filename, size_bytes}`
  - `POST /vault/retrieve` → `{cid}` → `{filename, content}`
  - `GET /lightning/balance` → `{balance_sats}`
  - `GET /identity/info` → `{npub, relays: [{url, connected}], last_broadcast}`
  - `GET /audit/recent?limit=50` → `{entries: [{ts, action, tool, ok, error}]}`
  - `GET /goose/status` → `{connected, pid, uptime_seconds, last_tool_call, total_calls}`

## Design System

| Token | Value |
|---|---|
| Background | `#000000` |
| GlassCard fill | `rgba(255,255,255,0.03)` |
| GlassCard border | `1px solid rgba(255,255,255,0.08)` |
| GlassCard blur | `backdrop-filter: blur(20px)` |
| GlassCard radius | `16px` |
| Primary text | `#FFFFFF` |
| Muted text | `rgba(255,255,255,0.5)` |
| Data font | `JetBrains Mono, monospace` |
| UI font | `Inter, system-ui, sans-serif` |
| Vault/IPFS | `#00F0FF` |
| Nostr/Identity | `#A855F7` |
| Lightning | `#F59E0B` |
| Goose/MCP | `#3B82F6` |
| Healthy | `#22C55E` |
| Error | `#EF4444` |

## Components

**GlassCard.tsx** — Reusable wrapper. Props: `children`, `className`, `accentColor`. Applies all glass tokens.

**StateOrb.tsx** — `@react-three/fiber` Canvas. Sphere with simplex noise displacement, animated via `useFrame`. Color from `systemState`: healthy=cyan pulse, warning=amber, error=red, disconnected=gray. Emissive glow.

**GooseStatus.tsx ★ (top-center)** — Brain heartbeat. Blue pulse = connected, gray = disconnected. Shows: uptime, last tool call + timestamp, total calls. Polls `/goose/status` 2s. Accent: blue.

**Dashboard.tsx** — CSS Grid. Orb ~40% center. 5 GlassCards: GooseStatus top-center, VaultPanel top-left, IdentityPanel top-right, LightningPanel bottom-left, AuditFeed bottom-right. Each uses `usePolling` (2s). Last-known data on failure with "stale" indicator.

**VaultPanel.tsx** — File count, pinned size, last action. Cyan. Link → `/vault`.

**IdentityPanel.tsx** — npub (truncated, copyable), relay dots (green/gray), last broadcast. Purple.

**LightningPanel.tsx** — Balance sats (large), daily spend bar vs limit, last payment. Amber.

**AuditFeed.tsx** — Scrollable 50 entries. Timestamp, action, tool badge (colored), success/fail. Auto-scroll.

**VaultExplorer.tsx (route /vault)** — 3D force-directed graph. Nodes=CIDs, cyan, sized by bytes. Click → detail slide-in: filename, full CID (copyable), size, stored_at, retrieve button.

**bridge.ts** — `API_BASE = "http://127.0.0.1:9473"`. Token from `~/MYKO/.session_token` via Tauri `fs`. `apiFetch<T>(path, opts)` with Bearer auth. Cache last response per endpoint for resilience.

**usePolling.ts** — `usePolling<T>(path, intervalMs) → {data, stale, error}`.

**useSessionToken.ts** — Read token once on mount via Tauri fs.

**types/api.ts** — TS interfaces matching backend Pydantic models.

## Tauri Config

- App: `MYKO`. Window: minimal chrome, 1280x800, dark.
- `main.rs`: on launch, spawn `python -m backend.bridge` as sidecar. On close, SIGTERM bridge.
- Permissions: fs read (`~/MYKO/.session_token`), localhost HTTP.
- CSP: no external URLs. Bundle Inter + JetBrains Mono fonts locally.
- No analytics, no telemetry, no CDN.

## Output

1. `backend/bridge.py` first. 2. Full frontend tree + every file with complete contents. 3. `package.json` pinned: react 19, @react-three/fiber, drei, three r165, tailwindcss, @tauri-apps/api. 4. `vite.config.ts`, `tailwind.config.ts`, `tauri.conf.json` fully configured. 5. No placeholders.
