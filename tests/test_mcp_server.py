"""MCP server: JSON-RPC protocol flow — initialize → tools/list → tools/call."""

from __future__ import annotations

import json

import pytest

from backend.mcp_server import PROTOCOL_VERSION, MCPServer


async def _echo(**kwargs) -> dict:
    return {"ok": True, "echo": kwargs}


async def _boom(**kwargs) -> dict:
    raise RuntimeError("deliberate explosion")


def _make_server() -> MCPServer:
    s = MCPServer()
    s.register_tool(
        "echo",
        "Echo tool.",
        {
            "type": "object",
            "properties": {"msg": {"type": "string"}},
            "required": ["msg"],
        },
        _echo,
    )
    s.register_tool(
        "boom",
        "Always fails.",
        {"type": "object", "properties": {}},
        _boom,
    )
    return s


@pytest.mark.asyncio
async def test_initialize_returns_expected_envelope():
    s = _make_server()
    resp = await s.handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert resp["id"] == 1
    assert resp["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert resp["result"]["serverInfo"]["name"] == "myko"
    assert "tools" in resp["result"]["capabilities"]


@pytest.mark.asyncio
async def test_notification_returns_none():
    s = _make_server()
    # notifications/initialized has no id → no response
    resp = await s.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert resp is None


@pytest.mark.asyncio
async def test_tools_list_returns_registered_tools():
    s = _make_server()
    resp = await s.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert names == {"echo", "boom"}
    for t in resp["result"]["tools"]:
        assert "description" in t
        assert "inputSchema" in t
        assert t["inputSchema"]["type"] == "object"


@pytest.mark.asyncio
async def test_tools_call_success():
    s = _make_server()
    resp = await s.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"msg": "hi"}},
        }
    )
    assert resp["id"] == 3
    content = resp["result"]["content"]
    assert content[0]["type"] == "text"
    payload = json.loads(content[0]["text"])
    assert payload == {"ok": True, "echo": {"msg": "hi"}}
    assert not resp["result"].get("isError", False)


@pytest.mark.asyncio
async def test_tools_call_unknown_tool_is_error():
    s = _make_server()
    resp = await s.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "does_not_exist", "arguments": {}},
        }
    )
    assert resp["result"]["isError"] is True
    assert "unknown tool" in resp["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_tools_call_handler_error_is_isolated():
    s = _make_server()
    resp = await s.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "boom", "arguments": {}},
        }
    )
    assert resp["result"]["isError"] is True
    assert "deliberate explosion" in resp["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_unknown_method_is_rpc_error():
    s = _make_server()
    resp = await s.handle_message({"jsonrpc": "2.0", "id": 6, "method": "does_not_exist"})
    assert "error" in resp
    assert resp["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_invalid_request_returns_error():
    s = _make_server()
    resp = await s.handle_message({"jsonrpc": "2.0", "id": 7})
    assert "error" in resp
    assert resp["error"]["code"] == -32600


@pytest.mark.asyncio
async def test_counters_track_tool_calls(tmp_path):
    s = MCPServer(status_path=tmp_path / ".goose_status.json")
    s.register_tool("echo", "echo", {"type": "object", "properties": {}}, _echo)
    assert s.total_calls == 0
    await s.handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "echo", "arguments": {}}}
    )
    assert s.total_calls == 1
    assert s.last_tool == "echo"
    status = json.loads((tmp_path / ".goose_status.json").read_text())
    assert status["total_calls"] == 1
    assert status["last_tool"] == "echo"
