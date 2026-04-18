"""MCP Protocol Server (stdio transport, JSON-RPC 2.0).

Goose spawns ``python -m backend.main`` as a subprocess and communicates via:
  * stdin  — incoming JSON-RPC requests / notifications (one per line)
  * stdout — JSON-RPC responses (one per line, flushed after each)
  * stderr — diagnostics only (never reserved for protocol traffic)

No external MCP SDK is used; this file implements the handshake and dispatch
directly (``initialize``, ``notifications/initialized``, ``tools/list``,
``tools/call``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from .logging_config import sha256_hex

log = logging.getLogger("myko.mcp")

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "myko"
SERVER_VERSION = "0.1.0"

# JSON-RPC error codes (subset)
ERR_PARSE = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    handler: Callable[..., Awaitable[dict]]


@dataclass
class MCPServer:
    tools: dict[str, Tool] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    total_calls: int = 0
    last_tool: str | None = None
    last_tool_ts: float | None = None
    status_path: Path | None = None

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: dict,
        handler: Callable[..., Awaitable[dict]],
    ) -> None:
        self.tools[name] = Tool(name, description, input_schema, handler)
        log.info(f"Registered tool: {name}")

    def _write_status(self) -> None:
        if self.status_path is None:
            return
        payload = {
            "pid": os.getpid(),
            "started_at": datetime.fromtimestamp(self.started_at, timezone.utc).isoformat(),
            "uptime_seconds": int(time.time() - self.started_at),
            "last_tool": self.last_tool,
            "last_tool_ts": (
                datetime.fromtimestamp(self.last_tool_ts, timezone.utc).isoformat()
                if self.last_tool_ts is not None
                else None
            ),
            "total_calls": self.total_calls,
        }
        try:
            self.status_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.status_path.with_name(self.status_path.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(str(tmp), str(self.status_path))
        except OSError as e:
            log.warning(f"Could not write status file: {e}")

    async def handle_message(self, msg: dict) -> dict | None:
        """Dispatch one JSON-RPC message. Returns a response dict, or ``None`` for notifications."""
        msg_id = msg.get("id")
        method = msg.get("method")
        params = msg.get("params") or {}
        is_notification = "id" not in msg or msg_id is None

        if not isinstance(method, str):
            if is_notification:
                return None
            return _error(msg_id, ERR_INVALID_REQUEST, "Missing or invalid 'method'")

        if method == "initialize":
            if is_notification:
                return None
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "capabilities": {"tools": {}},
                },
            }

        if method == "notifications/initialized":
            return None

        if method == "tools/list":
            if is_notification:
                return None
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": [
                        {
                            "name": t.name,
                            "description": t.description,
                            "inputSchema": t.input_schema,
                        }
                        for t in self.tools.values()
                    ]
                },
            }

        if method == "tools/call":
            if is_notification:
                return None
            return await self._dispatch_tool_call(msg_id, params)

        if method == "ping":
            if is_notification:
                return None
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

        if is_notification:
            return None
        return _error(msg_id, ERR_METHOD_NOT_FOUND, f"Method not found: {method}")

    async def _dispatch_tool_call(self, msg_id, params: dict) -> dict:
        name = params.get("name")
        args = params.get("arguments") or {}
        if not isinstance(name, str) or name not in self.tools:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: unknown tool {name!r}"}],
                    "isError": True,
                },
            }
        tool = self.tools[name]
        self.total_calls += 1
        self.last_tool = name
        self.last_tool_ts = time.time()
        self._write_status()

        try:
            result = await tool.handler(**args)
            payload = json.dumps(result, default=str, separators=(",", ":"))
            log.info(
                f"tool_ok {name}",
                extra={
                    "action": "tool_call",
                    "tool": name,
                    "input_hash": sha256_hex(args),
                    "output_hash": sha256_hex(payload),
                    "ok": True,
                },
            )
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": [{"type": "text", "text": payload}]},
            }
        except TypeError as e:
            msg = f"Invalid arguments for {name}: {e}"
            log.error(msg, extra={"action": "tool_call", "tool": name, "ok": False, "error": str(e)})
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {msg}"}],
                    "isError": True,
                },
            }
        except Exception as e:
            log.exception(
                f"tool_error {name}",
                extra={
                    "action": "tool_call",
                    "tool": name,
                    "input_hash": sha256_hex(args),
                    "ok": False,
                    "error": str(e),
                },
            )
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {e}"}],
                    "isError": True,
                },
            }

    async def run(self, stdin=None, stdout=None) -> None:
        """Run the stdin → dispatch → stdout loop until EOF."""
        loop = asyncio.get_event_loop()
        stdin_pipe = stdin if stdin is not None else os.fdopen(sys.stdin.fileno(), "rb", buffering=0)
        writer = stdout if stdout is not None else sys.stdout

        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, stdin_pipe)

        log.info(f"MCP server started; {len(self.tools)} tools registered")
        self._write_status()

        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                try:
                    msg = json.loads(text)
                except json.JSONDecodeError as e:
                    log.error(f"Bad JSON on stdin: {e}: {text[:120]!r}")
                    err = _error(None, ERR_PARSE, f"Parse error: {e}")
                    writer.write(json.dumps(err) + "\n")
                    writer.flush()
                    continue

                response = await self.handle_message(msg)
                if response is not None:
                    writer.write(json.dumps(response) + "\n")
                    writer.flush()
        finally:
            log.info("MCP server shutting down")


def _error(msg_id, code: int, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": code, "message": message},
    }
