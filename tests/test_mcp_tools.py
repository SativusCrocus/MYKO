"""Full 9-tool integration pass: schema validity + handler dispatch through the MCP server."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import jsonschema
import pytest

from backend.config import Settings
from backend.crypto import KeyManager
from backend.lightning import LNbitsWallet, PaymentResult
from backend.mcp_server import MCPServer
from backend.mcp_tools import (
    register_lightning_tools,
    register_nostr_tools,
    register_vault_tools,
)
from backend.models import RelayResponse, SignedEvent
from backend.nostr import NostrClient
from backend.vault import VaultManager
from tests.test_vault import FakeStorage


def _settings(tmp_path) -> Settings:
    return Settings(
        MYKO_PASSPHRASE="test-passphrase-1234",
        MYKO_HOME=tmp_path,
        LIGHTNING_BACKEND="lnbits",
        LIGHTNING_API_KEY="dummy",
        LIGHTNING_URL="http://127.0.0.1:5000",
    )


async def _build_full_server(tmp_path) -> tuple[MCPServer, VaultManager, NostrClient, LNbitsWallet]:
    settings = _settings(tmp_path)
    km = KeyManager(settings.MYKO_PASSPHRASE)
    storage = FakeStorage()
    vault = VaultManager(km, storage, tmp_path)
    nostr = NostrClient(vault, settings)
    wallet = LNbitsWallet(settings)
    server = MCPServer()
    register_vault_tools(server, vault, storage)
    register_nostr_tools(server, nostr)
    register_lightning_tools(server, wallet)
    return server, vault, nostr, wallet


@pytest.mark.asyncio
async def test_all_9_tools_registered(tmp_path):
    server, *_ = await _build_full_server(tmp_path)
    assert set(server.tools.keys()) == {
        "vault_store",
        "vault_retrieve",
        "vault_list",
        "ipfs_pin_directory",
        "nostr_broadcast",
        "nostr_encrypt_dm",
        "lightning_balance",
        "lightning_create_invoice",
        "lightning_pay",
    }


@pytest.mark.asyncio
async def test_every_input_schema_is_valid_json_schema(tmp_path):
    server, *_ = await _build_full_server(tmp_path)
    for name, tool in server.tools.items():
        # Raises on structural issues in the schema itself.
        jsonschema.Draft7Validator.check_schema(tool.input_schema)
        assert tool.input_schema.get("type") == "object", f"{name} must be object-typed"


@pytest.mark.asyncio
async def test_tools_list_returns_all_tools(tmp_path):
    server, *_ = await _build_full_server(tmp_path)
    resp = await server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert len(names) == 9


@pytest.mark.asyncio
async def test_vault_store_and_list_via_mcp(tmp_path):
    import base64

    server, vault, *_ = await _build_full_server(tmp_path)
    store_resp = await server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {
                "name": "vault_store",
                "arguments": {
                    "filename": "note.txt",
                    "content": base64.b64encode(b"hello").decode("ascii"),
                },
            },
        }
    )
    payload = json.loads(store_resp["result"]["content"][0]["text"])
    assert payload["filename"] == "note.txt"
    assert payload["size_bytes"] == 5

    list_resp = await server.handle_message(
        {"jsonrpc": "2.0", "id": 11, "method": "tools/call", "params": {"name": "vault_list", "arguments": {}}}
    )
    entries = json.loads(list_resp["result"]["content"][0]["text"])["entries"]
    assert len(entries) == 1
    assert entries[0]["filename"] == "note.txt"


@pytest.mark.asyncio
async def test_vault_store_rejects_bad_base64(tmp_path):
    server, *_ = await _build_full_server(tmp_path)
    resp = await server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {
                "name": "vault_store",
                "arguments": {"filename": "x.txt", "content": "!!! not base64 !!!"},
            },
        }
    )
    assert resp["result"]["isError"] is True


@pytest.mark.asyncio
async def test_nostr_broadcast_via_mcp(tmp_path):
    server, vault, nostr, _ = await _build_full_server(tmp_path)

    async def _fake_broadcast(event, relays=None):
        return [RelayResponse(relay_url="wss://relay.test", accepted=True)]

    with patch.object(nostr, "broadcast", side_effect=_fake_broadcast):
        resp = await server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 20,
                "method": "tools/call",
                "params": {
                    "name": "nostr_broadcast",
                    "arguments": {"kind": 1, "content": "hello world", "tags": []},
                },
            }
        )
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert len(payload["event_id"]) == 64
    assert payload["relays"][0]["accepted"] is True


@pytest.mark.asyncio
async def test_lightning_balance_via_mcp(tmp_path):
    server, _vault, _nostr, wallet = await _build_full_server(tmp_path)

    async def _fake_balance():
        return 777

    wallet.get_balance = _fake_balance  # type: ignore[assignment]
    resp = await server.handle_message(
        {"jsonrpc": "2.0", "id": 30, "method": "tools/call", "params": {"name": "lightning_balance", "arguments": {}}}
    )
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload == {"balance_sats": 777}


@pytest.mark.asyncio
async def test_lightning_pay_over_cap_returns_structured_error(tmp_path):
    server, _vault, _nostr, wallet = await _build_full_server(tmp_path)
    # amount decode mocked to 9999 > MAX_SATS_PER_TASK default of 1000
    with patch("backend.lightning._decode_invoice_amount_sats", return_value=9999):
        resp = await server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 40,
                "method": "tools/call",
                "params": {"name": "lightning_pay", "arguments": {"bolt11": "lnbc..."}},
            }
        )
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["success"] is False
    assert "per-task cap" in payload["error"]
