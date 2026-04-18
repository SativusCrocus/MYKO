"""LightningWallet — LND and LNbits backends with per-task and daily spend caps.

Common interface:
  * ``get_balance() -> int``
  * ``create_invoice(amount_sats, memo) -> bolt11_str``
  * ``pay_invoice(bolt11) -> PaymentResult``

Spend protection:
  * Per-task limit: ``MAX_SATS_PER_TASK`` (default 1000 sats).
  * Rolling-24h limit: ``MAX_DAILY_SATS`` (default 10000 sats).
  * In-memory spend ledger is pruned on each ``pay_invoice`` call.

Never log or return preimages; only ``payment_hash``.
"""

from __future__ import annotations

import abc
import base64
import logging
import ssl
import time
from pathlib import Path

import aiohttp
import bolt11 as bolt11lib
from pydantic import BaseModel, ConfigDict

from .config import Settings

log = logging.getLogger("myko.lightning")


class LightningError(Exception):
    pass


class PaymentResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    payment_hash: str | None = None
    amount_sats: int = 0
    error: str | None = None


def _decode_invoice_amount_sats(invoice: str) -> int:
    """Return the amount encoded in a BOLT11 invoice (sats, rounded up from msat)."""
    try:
        decoded = bolt11lib.decode(invoice)
    except Exception as e:
        raise LightningError(f"Could not decode BOLT11 invoice: {e}") from e
    amount_msat = getattr(decoded, "amount_msat", None)
    if amount_msat is None:
        raise LightningError("Invoice has no amount field — refusing to pay an ambiguous amount")
    # Round up to next satoshi.
    return (int(amount_msat) + 999) // 1000


class LightningWallet(abc.ABC):
    """Abstract base: concrete backends are LNDWallet and LNbitsWallet."""

    def __init__(self, config: Settings):
        self._config = config
        self._spend_ledger: list[tuple[float, int]] = []

    # ---------- abstract -----------------------------------------------

    @abc.abstractmethod
    async def get_balance(self) -> int: ...

    @abc.abstractmethod
    async def create_invoice(self, amount_sats: int, memo: str) -> str: ...

    @abc.abstractmethod
    async def _pay_invoice_raw(self, bolt11_str: str) -> tuple[bool, str | None, str | None]:
        """Backend-specific payment. Returns (success, payment_hash, error_msg)."""

    # ------------------------------------------------------------ spend

    def _prune_ledger(self, now: float) -> None:
        cutoff = now - 86_400
        self._spend_ledger = [(ts, amt) for ts, amt in self._spend_ledger if ts >= cutoff]

    def _spent_last_24h(self) -> int:
        return sum(amt for _ts, amt in self._spend_ledger)

    async def pay_invoice(self, bolt11_str: str) -> PaymentResult:
        amount_sats = _decode_invoice_amount_sats(bolt11_str)

        if amount_sats > self._config.MAX_SATS_PER_TASK:
            return PaymentResult(
                success=False,
                amount_sats=amount_sats,
                error=(
                    f"Invoice amount {amount_sats} sats exceeds per-task cap "
                    f"({self._config.MAX_SATS_PER_TASK} sats). Request explicit override."
                ),
            )

        now = time.time()
        self._prune_ledger(now)
        projected = self._spent_last_24h() + amount_sats
        if projected > self._config.MAX_DAILY_SATS:
            return PaymentResult(
                success=False,
                amount_sats=amount_sats,
                error=(
                    f"Payment of {amount_sats} sats would push rolling-24h spend to "
                    f"{projected} sats, above cap {self._config.MAX_DAILY_SATS}."
                ),
            )

        success, payment_hash, err = await self._pay_invoice_raw(bolt11_str)
        if success:
            self._spend_ledger.append((now, amount_sats))
            log.info(
                f"Lightning payment ok: hash={payment_hash} amount_sats={amount_sats}",
                extra={
                    "action": "lightning_pay",
                    "tool": "lightning_pay",
                    "ok": True,
                },
            )
        else:
            log.warning(
                f"Lightning payment failed: {err}",
                extra={"action": "lightning_pay", "tool": "lightning_pay", "ok": False, "error": err or ""},
            )
        return PaymentResult(
            success=success,
            payment_hash=payment_hash,
            amount_sats=amount_sats,
            error=err,
        )

    # ------------------------------------------------------------ factory

    @classmethod
    def create(cls, config: Settings) -> "LightningWallet":
        backend = config.LIGHTNING_BACKEND
        if backend == "lnd":
            return LNDWallet(config)
        if backend == "lnbits":
            return LNbitsWallet(config)
        raise LightningError(f"Unknown LIGHTNING_BACKEND: {backend}")


# ---------------------------------------------------------------------- LND


class LNDWallet(LightningWallet):
    """REST-based LND client (macaroon + self-signed TLS cert)."""

    def __init__(self, config: Settings):
        super().__init__(config)
        self._url = config.LIGHTNING_URL.rstrip("/")
        if not config.LIGHTNING_MACAROON_PATH:
            raise LightningError("LND backend requires LIGHTNING_MACAROON_PATH")
        self._macaroon_hex = Path(config.LIGHTNING_MACAROON_PATH).read_bytes().hex()
        self._ssl: ssl.SSLContext | bool = True
        if config.LIGHTNING_TLS_CERT_PATH:
            ctx = ssl.create_default_context(cafile=str(config.LIGHTNING_TLS_CERT_PATH))
            # LND uses a self-signed cert with hostname=localhost; keep strict verify via the cafile.
            self._ssl = ctx

    def _headers(self) -> dict[str, str]:
        return {"Grpc-Metadata-macaroon": self._macaroon_hex}

    async def _request(self, method: str, path: str, *, json_body=None) -> dict:
        url = f"{self._url}{path}"
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method, url, headers=self._headers(), json=json_body, ssl=self._ssl
            ) as resp:
                body = await resp.json(content_type=None)
                if resp.status != 200:
                    raise LightningError(f"LND {method} {path} returned {resp.status}: {body}")
                return body

    async def get_balance(self) -> int:
        data = await self._request("GET", "/v1/balance/channels")
        return int(data.get("balance") or data.get("local_balance", {}).get("sat") or 0)

    async def create_invoice(self, amount_sats: int, memo: str) -> str:
        data = await self._request(
            "POST",
            "/v1/invoices",
            json_body={"value": str(amount_sats), "memo": memo},
        )
        bolt11_str = data.get("payment_request")
        if not bolt11_str:
            raise LightningError(f"LND response missing payment_request: {data}")
        return bolt11_str

    async def _pay_invoice_raw(self, bolt11_str: str) -> tuple[bool, str | None, str | None]:
        try:
            data = await self._request(
                "POST",
                "/v1/channels/transactions",
                json_body={"payment_request": bolt11_str},
            )
        except LightningError as e:
            return False, None, str(e)
        err = data.get("payment_error")
        if err:
            return False, None, err
        preimage_b64 = data.get("payment_preimage")
        hash_hex: str | None = None
        if data.get("payment_hash"):
            raw = data["payment_hash"]
            # LND REST returns base64-encoded bytes — normalize to hex.
            try:
                hash_hex = base64.b64decode(raw).hex()
            except (ValueError, TypeError):
                hash_hex = str(raw)
        # Never log / return the preimage; intentionally discard it.
        del preimage_b64
        return True, hash_hex, None


# ------------------------------------------------------------------- LNbits


class LNbitsWallet(LightningWallet):
    """REST-based LNbits client (API key header)."""

    def __init__(self, config: Settings):
        super().__init__(config)
        self._url = config.LIGHTNING_URL.rstrip("/")
        if not config.LIGHTNING_API_KEY:
            raise LightningError("LNbits backend requires LIGHTNING_API_KEY")
        self._api_key = config.LIGHTNING_API_KEY

    def _headers(self) -> dict[str, str]:
        return {"X-Api-Key": self._api_key, "Content-Type": "application/json"}

    async def _request(self, method: str, path: str, *, json_body=None) -> dict:
        url = f"{self._url}{path}"
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(method, url, headers=self._headers(), json=json_body) as resp:
                body = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise LightningError(f"LNbits {method} {path} returned {resp.status}: {body}")
                return body

    async def get_balance(self) -> int:
        data = await self._request("GET", "/api/v1/wallet")
        # LNbits reports balance in millisats.
        return int(data.get("balance", 0)) // 1000

    async def create_invoice(self, amount_sats: int, memo: str) -> str:
        data = await self._request(
            "POST",
            "/api/v1/payments",
            json_body={"out": False, "amount": int(amount_sats), "memo": memo},
        )
        bolt11_str = data.get("bolt11") or data.get("payment_request")
        if not bolt11_str:
            raise LightningError(f"LNbits response missing bolt11: {data}")
        return bolt11_str

    async def _pay_invoice_raw(self, bolt11_str: str) -> tuple[bool, str | None, str | None]:
        try:
            data = await self._request(
                "POST",
                "/api/v1/payments",
                json_body={"out": True, "bolt11": bolt11_str},
            )
        except LightningError as e:
            return False, None, str(e)
        hash_hex = data.get("payment_hash") or data.get("checking_id")
        if not hash_hex:
            return False, None, f"LNbits response missing payment_hash: {data}"
        return True, hash_hex, None
