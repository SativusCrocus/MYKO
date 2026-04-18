"""Security primitives: secure memory wipe, constant-time compare, optional YubiKey challenge."""

from __future__ import annotations

import hmac
import shutil
import subprocess
from typing import Iterable


def secure_wipe(buf: bytearray | Iterable[bytearray]) -> None:
    """Overwrite a mutable byte buffer with zeros in place.

    Python cannot guarantee zeroing due to the garbage collector potentially
    copying objects, but this reduces the window for memory-dump attacks.
    Callers must use ``bytearray`` (not immutable ``bytes``) for this to work.
    """
    if isinstance(buf, bytearray):
        for i in range(len(buf)):
            buf[i] = 0
        return
    for b in buf:
        if isinstance(b, bytearray):
            for i in range(len(b)):
                b[i] = 0


def constant_time_compare(a: bytes | str, b: bytes | str) -> bool:
    """Timing-safe equality check for tokens, tags, hashes."""
    if isinstance(a, str):
        a = a.encode("utf-8")
    if isinstance(b, str):
        b = b.encode("utf-8")
    return hmac.compare_digest(a, b)


def yubikey_challenge(challenge: bytes, slot: int = 2, timeout: float = 5.0) -> bytes | None:
    """HMAC-SHA256 challenge-response via the ``ykman`` CLI.

    Returns the 20-byte response bytes, or ``None`` if:
      * ``ykman`` is not installed
      * no YubiKey is inserted
      * the slot is unconfigured or the command times out

    Callers should treat ``None`` as "fall back to passphrase-only derivation".
    """
    if shutil.which("ykman") is None:
        return None
    if slot not in (1, 2):
        return None
    try:
        result = subprocess.run(
            ["ykman", "otp", "calculate", str(slot), challenge.hex()],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
    response_hex = result.stdout.strip()
    try:
        return bytes.fromhex(response_hex)
    except ValueError:
        return None
