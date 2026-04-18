# MYKO — Sovereign Life OS

Local-first, decentralized Life OS. Goose is the brain. The user owns every key. AI executes, never controls.

MYKO exposes five sovereign layers as MCP tools: an encrypted IPFS vault (memory), Nostr identity (identity), Bitcoin Lightning (value), and — via a separate FastAPI bridge — a Tauri + React + Three.js dashboard (interface). All layers run as two local processes on your machine.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   User's Machine                │
│                                                 │
│  ┌──────────┐    stdio     ┌──────────────────┐ │
│  │  Goose   │◄────────────►│  MCP Server      │ │
│  │  (LLM)   │              │  (backend.main)  │ │
│  └──────────┘              └────────┬─────────┘ │
│                                     │ imports    │
│  ┌──────────┐    HTTP      ┌────────┴─────────┐ │
│  │  Tauri   │◄────────────►│  Bridge Server   │ │
│  │  (UI)    │  :9473       │  (backend.bridge)│ │
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
│              logs/                                │
└─────────────────────────────────────────────────┘
```

## Prerequisites

- Python 3.12+
- Node.js 20+
- Rust + Cargo (for the Tauri desktop shell)
- A running **Kubo (IPFS)** node — default RPC at `http://127.0.0.1:5001/api/v0`
- A running **LND** or **LNbits** instance (for Lightning)
- **Goose** installed and able to register MCP servers
- *Optional:* a YubiKey + the `ykman` CLI, for hardware-bound master-key derivation

## Install

### Backend

```bash
cd /path/to/myko
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Frontend

```bash
cd frontend
npm install
```

## Configure

```bash
cp .env.example .env
# Fill in MYKO_PASSPHRASE, LIGHTNING_*, etc.
chmod 600 .env
```

Update `goose/goose_config.yaml` — replace `/absolute/path/to/myko` with the real absolute path to your checkout.

## Register with Goose

Goose discovers MCP servers from a config file. Using the bundled profile:

```bash
# Confirm the exact command against your installed Goose version.
goose configure add-mcp ./goose/goose_config.yaml
```

Consult `goose --help` or the [Goose documentation](https://block.github.io/goose/) if that subcommand differs on your version. At minimum, Goose must be told to spawn `python -m backend.main` with the env vars listed in `goose_config.yaml`.

## Run

1. **Kubo (IPFS):**
   ```bash
   ipfs daemon
   ```
2. **Lightning node:** start LND or LNbits per its own docs.
3. **Bridge server** (used by the Tauri UI):
   ```bash
   python -m backend.bridge
   ```
4. **Tauri app:**
   ```bash
   cd frontend && npm run tauri dev
   ```
5. **MCP server:** Goose spawns it automatically on the first tool call — you do not start it manually.

## Verify

1. Run the test suite:
   ```bash
   pytest tests/ -v
   ```
2. Ask Goose: *"Store a file called hello.txt with the content 'hi' in the vault."* → *"List the vault."* → *"Retrieve hello.txt."* — the file should roundtrip through encryption and IPFS.
3. Watch the MYKO dashboard: the GooseStatus panel pulses blue on each tool call, and the audit feed shows the three vault actions.

## Security Hardening

1. **Hardware key (YubiKey):** set `YUBIKEY_ENABLED=true`. The master key is then derived from `passphrase ‖ HMAC-SHA256(yubikey, salt)`. Requires `ykman` on PATH. Without the physical YubiKey, the vault cannot be decrypted.
2. **Memory wiping:** all sensitive byte buffers are overwritten with zeros via `secure_wipe()` in `finally` blocks. Note: Python's garbage collector may have copied intermediate values, so this reduces — but does not eliminate — the window for memory-dump attacks.
3. **Constant-time comparisons:** session-token and HMAC validation use `hmac.compare_digest` to resist timing side-channels.
4. **Process sandboxing** *(recommended, not enforced)*:
   - Linux: run under a dedicated user, e.g. `sudo -u myko python -m backend.main`.
   - Linux: wrap with `firejail`:
     ```bash
     firejail --private=/home/myko --net=none \
         python -m backend.main
     ```
   - Linux: alternatively, `bwrap` / bubblewrap for unprivileged namespaces.
   - macOS: use `sandbox-exec` with a custom SBPL profile.
5. **No secrets in logs:** the audit log only contains SHA-256 hashes of tool inputs/outputs. Never payment preimages, passphrases, macaroons, or plaintext.
6. **File permissions:** `.env`, `manifest.enc`, and `.session_token` are all written with mode `0600`. Verify with `ls -l ~/MYKO/`.
7. **Localhost only:** the bridge binds to `127.0.0.1`. CORS is restricted to `tauri://localhost`. No external URLs are allowed in the Tauri CSP.

## File Layout

```
myko/
├── backend/                    # Python: MCP server, vault, Nostr, Lightning, bridge
├── frontend/                   # React + Three.js Tauri desktop app
├── goose/                      # Goose profile + sovereign manifesto
├── tests/                      # pytest suites
├── requirements.txt
├── .env.example
└── README.md                   # this file
```

## Tool Registry

| Tool | Purpose |
|---|---|
| `vault_store` | Encrypt + pin a file to the IPFS-backed vault. |
| `vault_retrieve` | Fetch + decrypt a file by CID. |
| `vault_list` | List all vault entries. |
| `ipfs_pin_directory` | Hash + pin an entire local directory. |
| `nostr_broadcast` | Sign + broadcast a Nostr event (supports NIP-13 PoW). |
| `nostr_encrypt_dm` | Send an NIP-17 gift-wrapped, NIP-44 encrypted DM. |
| `lightning_balance` | Report current Lightning balance in sats. |
| `lightning_create_invoice` | Create a BOLT11 invoice. |
| `lightning_pay` | Pay a BOLT11 invoice, gated by per-task + daily spend caps. |

## License

See project root for license.
