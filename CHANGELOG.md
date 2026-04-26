# Changelog

All notable changes to MYKO are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This file is maintained by
[release-please](https://github.com/googleapis/release-please) from
[Conventional Commits](https://www.conventionalcommits.org) on `main`. Release
artifacts (source archive, CycloneDX + SPDX SBOMs, Sigstore build provenance
attestation) are produced by the `release.yml` workflow on every `v*.*.*` tag
and verifiable with `gh attestation verify`.

## [0.1.0](https://github.com/SativusCrocus/MYKO/releases/tag/v0.1.0) (2026-04-20)

First public release. MYKO is a local-first, decentralized Life OS — encrypted
IPFS vault, Nostr identity, Bitcoin Lightning — with the user owning every key
and AI executing through capped MCP tools.

### Features

- **Brain + Memory** — MCP server (stdio JSON-RPC 2.0) plus an encrypted
  manifest vault (PBKDF2-SHA256 600 000 iterations → AES-256-GCM) backed by a
  local Kubo / IPFS node. Cross-process safe via `fcntl.flock`.
- **Identity** — Nostr with full BIP-340 Schnorr, NIP-01 canonical
  serialization, NIP-13 PoW, NIP-44 v2 encryption, and NIP-17 gift-wrapped DMs.
  Validated against the official NIP-44 paulmillr test vectors.
- **Value** — Bitcoin Lightning via LND (macaroon + TLS) or LNbits (API key).
  Per-task and rolling-24-hour spend caps enforced on every call and persisted
  atomically to `~/MYKO/.spend_ledger.json` so a restart cannot reset them.
- **Interface** — Tauri 2 desktop shell with a React 19 + Three.js dashboard.
  FastAPI bridge on `127.0.0.1:9473`, 64-hex bearer token at
  `~/MYKO/.session_token` (mode 0600), CORS locked to `tauri://localhost`.
- **MCP tools** — `vault_store`, `vault_retrieve`, `vault_list`,
  `ipfs_pin_directory`, `nostr_broadcast`, `nostr_encrypt_dm`,
  `lightning_balance`, `lightning_create_invoice`, `lightning_pay`.

### Security

- PBKDF2-SHA256 with 600 000 iterations and unique salt per encryption.
- AES-256-GCM authenticates every byte.
- Optional YubiKey hardware factor mixed via HMAC-SHA256.
- `secure_wipe()` in `finally` blocks zeroes sensitive buffers.
- `hmac.compare_digest` on session-token and HMAC paths.
- Bridge binds to `127.0.0.1` only; Tauri CSP rejects external URLs.
- Audit log stores SHA-256 hashes of tool inputs and outputs — never
  preimages, macaroons, or plaintext.
- `.env`, `manifest.enc`, `.session_token` written `0600`.

### Verified

- 173 pytest tests passing across crypto, storage, vault, Nostr, Lightning,
  and MCP modules.
- Frontend `tsc --noEmit` clean.
- CI matrix covers Python 3.12 and 3.13.
- E2E acceptance script (`scripts/e2e_vault.py`) round-trips a payload
  through a live Kubo daemon.
