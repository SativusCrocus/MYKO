# Security policy

MYKO holds keys, money, and identity on behalf of its user. We treat security
issues as the highest priority class of bug. This document describes our
threat model, what we consider in and out of scope, and how to report a
vulnerability privately.

## Reporting a vulnerability

**Do not open a public GitHub issue.** Use one of the channels below:

1. **GitHub Private Vulnerability Reporting** — preferred.
   <https://github.com/SativusCrocus/MYKO/security/advisories/new>

2. **Encrypted Nostr DM** to the maintainer's project npub (NIP-17 gift-wrapped,
   NIP-44 v2 encrypted). The current npub is published in the latest GitHub
   Release notes and signed-tagged on the repo.

We aim to:

| Severity | First response | Triaged | Patch |
|---|---|---|---|
| **Critical** | within 24 h | within 72 h | within 7 days |
| **High** | within 72 h | within 7 days | within 30 days |
| **Medium** | within 7 days | within 14 days | next minor release |
| **Low** | within 14 days | next minor release | next minor release |

We will credit you in the release notes unless you ask otherwise.

## Severity classification

| Class | Examples |
|---|---|
| **Critical** | Vault decryption without passphrase. Bridge auth bypass on `127.0.0.1`. Spend-cap bypass that drains a Lightning wallet. Cryptographic key recovery from public artifacts. |
| **High** | LLM-driven exfiltration of plaintext vault contents. Audit log forgery that hides a tool call from the user. Macaroon / LNbits API key leakage to logs. Cross-process race that lets two MYKO instances corrupt the manifest. |
| **Medium** | Constant-time bypass on session-token compare. Padding-oracle on NIP-44 ciphertext. Weak randomness in salt or nonce paths. Frontend XSS via vault filename rendering. |
| **Low** | Verbose error messages leaking install paths. Missing security header on the static landing page. Outdated dependency with no exploitable code path in MYKO. |

## In-scope threat model

We defend against:

- **A malicious LLM driving the MCP tools.** Spend caps, per-tool rate limits,
  audit logging, and the Tauri UI's cap-denial surface are the layered
  controls. Prompt injection cannot exceed `MAX_SATS_PER_TASK`,
  `MAX_DAILY_SATS`, or unlock the YubiKey factor.
- **A network adversary** between MYKO and its Lightning / IPFS / Nostr
  endpoints. TLS for LND, macaroon auth, and signed Nostr events are the
  primary controls. The bridge binds only to `127.0.0.1`; nothing MYKO ships
  listens on a public interface.
- **A passive observer of the encrypted vault on disk or pinned to IPFS.**
  PBKDF2-SHA256 (600 000 iterations) + AES-256-GCM with unique salt per
  encryption is the baseline. Optional YubiKey HMAC factor adds hardware
  binding.
- **A local non-root attacker on the same machine.** `0600` permissions on
  `.env`, `manifest.enc`, `.session_token`. Constant-time compares on the
  bridge bearer token. The audit log records hashed inputs / outputs only.
- **A compromised dependency in the supply chain.** Pinned hashes in
  `requirements.txt` (planned), pinned SHA references for GitHub Actions,
  Dependabot review on every minor/patch bump, CodeQL on every push.

## Out-of-scope threat model

We do **not** claim to defend against:

- A **compromised host** — root user, kernel-level malware, cold-boot or evil-
  maid attacks, or a debugger attached to the running MYKO process.
- A **compromised hardware path** — CPU side channels, firmware implants,
  hardware keyloggers.
- A **lost passphrase or YubiKey without backup**. There is currently no
  recovery primitive; this is a documented limitation tracked for v0.2.
- **Censorship** of IPFS gateways, Nostr relays, or Lightning routes. MYKO is
  designed for resilience (multi-relay, multi-route) but does not promise
  uncensorable delivery.
- The **user's choice of LLM**. The promise is that the LLM cannot exceed the
  configured caps — not that the LLM is itself trustworthy.
- **Physical coercion** of the user.

## Cryptographic posture

| Primitive | Construction | Source |
|---|---|---|
| Key derivation | PBKDF2-SHA256, 600 000 iterations, 32-byte random salt per encryption | `backend/crypto.py` |
| Symmetric encryption | AES-256-GCM with random 96-bit nonce, AAD = key fingerprint | `backend/crypto.py` |
| Optional hardware factor | HMAC-SHA256(challenge, salt) over a YubiKey slot, mixed into the master key | `backend/crypto.py` |
| Identity | Nostr BIP-340 Schnorr; NIP-01 canonical serialization; NIP-13 PoW; NIP-44 v2 encryption; NIP-17 gift wrap | `backend/nostr.py` |
| NIP-44 conformance | Validated against the official paulmillr test vectors on every CI run | `tests/test_nip44_vectors.py`, `tests/vectors/nip44.vectors.json` |
| Constant-time compare | `hmac.compare_digest` for session-token and HMAC paths | `backend/bridge.py` |

## Build & supply-chain integrity

- **Pinned GitHub Actions** to commit SHAs in every workflow.
- **Dependabot** opens PRs weekly for `pip`, `npm`, `cargo`, and
  `github-actions` ecosystems.
- **CodeQL** scans Python and JavaScript / TypeScript on every push and PR.
- **Reproducible release builds** with hash-pinned `requirements.txt` and
  committed `package-lock.json` / `Cargo.lock` (planned for v0.2).
- **Build provenance** via SLSA attestation on every tagged release (planned
  for v0.2).

## Disclosure history

No vulnerabilities have been disclosed yet. This section will list each
advisory's CVE (where assigned), the affected version range, the credited
reporter, and a link to the GitHub Security Advisory once the embargo ends.

---

*Last updated: 2026-04-20*
