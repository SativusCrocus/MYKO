"""LightningWallet: spend caps, rolling-24h, factory selection, backend isolation."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.config import Settings
from backend.lightning import (
    LightningError,
    LightningWallet,
    LNbitsWallet,
    LNDWallet,
    PaymentResult,
    _decode_invoice_amount_sats,
)


def _settings(**overrides) -> Settings:
    base = {
        "MYKO_PASSPHRASE": "test-passphrase-1234",
        "LIGHTNING_BACKEND": "lnbits",
        "LIGHTNING_URL": "http://127.0.0.1:5000",
        "LIGHTNING_API_KEY": "dummy-api-key",
        "MAX_SATS_PER_TASK": 1000,
        "MAX_DAILY_SATS": 5000,
    }
    base.update(overrides)
    return Settings(**base)


# ---------------------------------------------------------------- factory


def test_factory_returns_lnbits_by_default():
    settings = _settings()
    wallet = LightningWallet.create(settings)
    assert isinstance(wallet, LNbitsWallet)


def test_factory_lnd_requires_macaroon(tmp_path):
    with pytest.raises(LightningError):
        LightningWallet.create(_settings(LIGHTNING_BACKEND="lnd"))


def test_factory_lnd_ok_with_macaroon(tmp_path):
    macaroon = tmp_path / "admin.macaroon"
    macaroon.write_bytes(b"\x01\x02\x03")
    wallet = LightningWallet.create(
        _settings(LIGHTNING_BACKEND="lnd", LIGHTNING_MACAROON_PATH=macaroon)
    )
    assert isinstance(wallet, LNDWallet)


def test_factory_unknown_backend_rejected():
    # Pydantic catches the literal-type violation before our factory does.
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _settings(LIGHTNING_BACKEND="invalid")


# -------------------------------------------------------------- decoding


def test_decode_amount_rejects_amountless_invoice():
    # A valid BOLT11 with no amount (uses "lnbc" prefix with no amount field).
    # We exercise the error branch with a clearly invalid payload.
    with pytest.raises(LightningError):
        _decode_invoice_amount_sats("not-a-real-invoice")


# ---------------------------------------------------------- spend caps


@pytest.mark.asyncio
async def test_rejects_over_per_task_cap():
    wallet = LNbitsWallet(_settings(MAX_SATS_PER_TASK=500))

    async def _ignore_raw(_):
        raise AssertionError("pay_invoice_raw must not be called when the cap rejects")

    wallet._pay_invoice_raw = _ignore_raw  # type: ignore[assignment]

    with patch("backend.lightning._decode_invoice_amount_sats", return_value=1000):
        result = await wallet.pay_invoice("lnbc-dummy")
    assert result.success is False
    assert "per-task cap" in (result.error or "")


@pytest.mark.asyncio
async def test_rejects_over_daily_cap():
    wallet = LNbitsWallet(_settings(MAX_SATS_PER_TASK=1000, MAX_DAILY_SATS=1500))

    async def _ok(_):
        return True, "hashA", None

    wallet._pay_invoice_raw = _ok  # type: ignore[assignment]

    with patch("backend.lightning._decode_invoice_amount_sats", return_value=1000):
        r1 = await wallet.pay_invoice("x")
        r2 = await wallet.pay_invoice("y")
    assert r1.success is True
    assert r2.success is False
    assert "rolling-24h" in (r2.error or "")


@pytest.mark.asyncio
async def test_ledger_prunes_old_entries():
    wallet = LNbitsWallet(_settings(MAX_SATS_PER_TASK=1000, MAX_DAILY_SATS=1500))
    # Seed an "old" spend older than 24h.
    wallet._spend_ledger.append((time.time() - 86_500, 1000))

    async def _ok(_):
        return True, "hashNew", None

    wallet._pay_invoice_raw = _ok  # type: ignore[assignment]

    with patch("backend.lightning._decode_invoice_amount_sats", return_value=1000):
        result = await wallet.pay_invoice("z")
    assert result.success is True
    # Old entry was pruned; only the new one remains.
    assert len(wallet._spend_ledger) == 1


@pytest.mark.asyncio
async def test_failure_does_not_record_spend():
    wallet = LNbitsWallet(_settings(MAX_SATS_PER_TASK=1000, MAX_DAILY_SATS=5000))

    async def _fail(_):
        return False, None, "route not found"

    wallet._pay_invoice_raw = _fail  # type: ignore[assignment]

    with patch("backend.lightning._decode_invoice_amount_sats", return_value=500):
        result = await wallet.pay_invoice("bad")
    assert result.success is False
    assert result.error == "route not found"
    assert wallet._spend_ledger == []


# ----------------------------------------------------------- LNbits surface


@pytest.mark.asyncio
async def test_lnbits_balance_divides_msat():
    wallet = LNbitsWallet(_settings())

    async def _req(method, path, json_body=None):
        assert method == "GET" and path == "/api/v1/wallet"
        return {"balance": 12_345_000}  # msat

    wallet._request = _req  # type: ignore[assignment]
    sats = await wallet.get_balance()
    assert sats == 12_345


@pytest.mark.asyncio
async def test_lnbits_create_invoice_returns_bolt11():
    wallet = LNbitsWallet(_settings())

    async def _req(method, path, json_body=None):
        assert method == "POST" and path == "/api/v1/payments"
        assert json_body == {"out": False, "amount": 250, "memo": "coffee"}
        return {"bolt11": "lnbc250n1p..."}

    wallet._request = _req  # type: ignore[assignment]
    bolt11_str = await wallet.create_invoice(250, "coffee")
    assert bolt11_str == "lnbc250n1p..."


@pytest.mark.asyncio
async def test_lnbits_pay_raw_extracts_hash():
    wallet = LNbitsWallet(_settings())

    async def _req(method, path, json_body=None):
        return {"payment_hash": "abc123"}

    wallet._request = _req  # type: ignore[assignment]
    ok, hash_hex, err = await wallet._pay_invoice_raw("lnbc...")
    assert ok is True
    assert hash_hex == "abc123"
    assert err is None


# -------------------------------------------------------------- LND surface


@pytest.mark.asyncio
async def test_lnd_balance_parses_response(tmp_path):
    macaroon = tmp_path / "admin.macaroon"
    macaroon.write_bytes(b"\x01\x02")
    wallet = LNDWallet(_settings(LIGHTNING_BACKEND="lnd", LIGHTNING_MACAROON_PATH=macaroon))

    async def _req(method, path, json_body=None):
        assert path == "/v1/balance/channels"
        return {"balance": "42"}

    wallet._request = _req  # type: ignore[assignment]
    sats = await wallet.get_balance()
    assert sats == 42


@pytest.mark.asyncio
async def test_lnd_pay_raw_discards_preimage(tmp_path):
    macaroon = tmp_path / "admin.macaroon"
    macaroon.write_bytes(b"\x01")
    wallet = LNDWallet(_settings(LIGHTNING_BACKEND="lnd", LIGHTNING_MACAROON_PATH=macaroon))

    import base64

    hash_bytes = bytes.fromhex("deadbeef" * 8)
    preimage_bytes = b"\xab" * 32

    async def _req(method, path, json_body=None):
        return {
            "payment_hash": base64.b64encode(hash_bytes).decode("ascii"),
            "payment_preimage": base64.b64encode(preimage_bytes).decode("ascii"),
            "payment_error": "",
        }

    wallet._request = _req  # type: ignore[assignment]
    ok, hash_hex, err = await wallet._pay_invoice_raw("lnbc...")
    assert ok is True
    assert hash_hex == hash_bytes.hex()
    assert err is None
