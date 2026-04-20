#!/usr/bin/env python3
"""End-to-end acceptance test for the MYKO vault.

Exercises the full path that Goose would drive through MCP, but directly
against the backend API so it runs without the LLM in the loop:

    store random payload  →  list  →  find CID  →  retrieve  →  byte-compare

Requires a running Kubo (IPFS) daemon at ``IPFS_API_URL`` (default
``http://127.0.0.1:5001/api/v0``). Everything else is mocked out: no Goose,
no Lightning, no Tauri — just vault correctness.

Usage::

    MYKO_PASSPHRASE=test-e2e-pw \
        python scripts/e2e_vault.py              # stores a generated blob
    python scripts/e2e_vault.py --file path.bin  # stores a specific file

Exit code 0 on success, non-zero on any mismatch or upstream error.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import sys
import tempfile
from pathlib import Path

# Allow running as a script without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import Settings
from backend.crypto import KeyManager
from backend.storage import StorageEngine
from backend.vault import VaultManager


async def _run(filename: str, payload: bytes) -> int:
    # Isolated MYKO_HOME so we don't clobber the user's real manifest.
    with tempfile.TemporaryDirectory(prefix="myko-e2e-") as tmpdir:
        os.environ.setdefault("MYKO_PASSPHRASE", "e2e-test-passphrase-not-secret")
        os.environ["MYKO_HOME"] = tmpdir
        settings = Settings()

        key_mgr = KeyManager(settings.MYKO_PASSPHRASE)
        async with StorageEngine(settings.IPFS_API_URL) as storage:
            vault = VaultManager(key_mgr, storage, settings.MYKO_HOME)

            print(f"→ storing {len(payload)} bytes as {filename!r}")
            stored = await vault.store(filename, payload)
            print(f"  CID:   {stored.cid}")
            print(f"  bytes: {stored.size_bytes}")

            print("→ listing vault")
            entries = await vault.list()
            if not any(e.cid == stored.cid for e in entries):
                print(f"FAIL: stored CID {stored.cid} not found in manifest", file=sys.stderr)
                return 1
            print(f"  {len(entries)} entries, stored CID present ✓")

            print("→ retrieving + decrypting")
            recovered = await vault.retrieve(stored.cid)
            if recovered != payload:
                print(
                    f"FAIL: plaintext mismatch "
                    f"(orig {len(payload)}B vs got {len(recovered)}B)",
                    file=sys.stderr,
                )
                return 2
            print(f"  {len(recovered)} bytes recovered ✓")
            print(f"  plaintext matches original ✓")

    print("\nE2E PASS")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Path to a local file to store. If omitted, a 4KiB random payload is used.",
    )
    ap.add_argument(
        "--name",
        default="e2e-hello.bin",
        help="Filename to record in the vault manifest.",
    )
    args = ap.parse_args()

    if args.file:
        payload = args.file.read_bytes()
        filename = args.file.name
    else:
        payload = secrets.token_bytes(4096)
        filename = args.name

    rc = asyncio.run(_run(filename, payload))
    sys.exit(rc)


if __name__ == "__main__":
    main()
