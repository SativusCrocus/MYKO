"""Tool registry — JSON Schemas + async handlers that Goose calls.

All handlers receive pre-validated kwargs from ``tools/call``. Each handler
returns a JSON-serializable ``dict`` which the MCP server wraps as the
``content[0].text`` of the tool-call response.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import TYPE_CHECKING

from .storage import StorageEngine
from .vault import VaultManager

if TYPE_CHECKING:
    from .lightning import LightningWallet
    from .mcp_server import MCPServer
    from .nostr import NostrClient

log = logging.getLogger("myko.tools")


# ---------------------------------------------------------------- vault tools


def register_vault_tools(server: "MCPServer", vault: VaultManager, storage: StorageEngine) -> None:
    async def vault_store(filename: str, content: str) -> dict:
        try:
            data = base64.b64decode(content, validate=True)
        except ValueError as e:
            raise ValueError(f"content must be valid base64: {e}") from e
        entry = await vault.store(filename, data)
        return {
            "cid": entry.cid,
            "filename": entry.filename,
            "size_bytes": entry.size_bytes,
            "stored_at": entry.stored_at.isoformat(),
        }

    async def vault_retrieve(cid: str) -> dict:
        plaintext = await vault.retrieve(cid)
        match = await vault.find_by_cid(cid)
        filename = match.filename if match else "unknown"
        return {
            "filename": filename,
            "content": base64.b64encode(plaintext).decode("ascii"),
            "size_bytes": len(plaintext),
        }

    async def vault_list() -> dict:
        entries = await vault.list()
        return {"entries": [e.model_dump(mode="json") for e in entries]}

    async def ipfs_pin_directory(path: str) -> dict:
        root_cid = await storage.pin_directory(path)
        file_count = 0
        for _, _, files in os.walk(path):
            file_count += len(files)
        return {"root_cid": root_cid, "file_count": file_count}

    server.register_tool(
        "vault_store",
        "Encrypt and permanently store a file in the MYKO vault. Use when the user wants to save, back up, remember, or archive data.",
        {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Human-readable name for the file."},
                "content": {"type": "string", "description": "File contents, base64-encoded."},
            },
            "required": ["filename", "content"],
            "additionalProperties": False,
        },
        vault_store,
    )
    server.register_tool(
        "vault_retrieve",
        "Fetch and decrypt a previously stored file by its CID.",
        {
            "type": "object",
            "properties": {
                "cid": {"type": "string", "description": "Content identifier returned by vault_store."},
            },
            "required": ["cid"],
            "additionalProperties": False,
        },
        vault_retrieve,
    )
    server.register_tool(
        "vault_list",
        "List all files in the vault with CIDs and metadata.",
        {"type": "object", "properties": {}, "additionalProperties": False},
        vault_list,
    )
    server.register_tool(
        "ipfs_pin_directory",
        "Hash and pin an entire local directory to IPFS for permanent storage.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to a local directory."},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        ipfs_pin_directory,
    )


# ---------------------------------------------------------------- nostr tools


def register_nostr_tools(server: "MCPServer", nostr: "NostrClient") -> None:
    async def nostr_broadcast(
        kind: int,
        content: str,
        tags: list[list[str]] | None = None,
        pow_target: int | None = None,
    ) -> dict:
        event = await nostr.create_event(
            kind=int(kind),
            content=content,
            tags=tags or [],
            pow_target=int(pow_target) if pow_target else None,
        )
        responses = await nostr.broadcast(event)
        return {
            "event_id": event.id,
            "pubkey": event.pubkey,
            "relays": [r.model_dump(mode="json") for r in responses],
        }

    async def nostr_encrypt_dm(recipient_pubkey: str, plaintext: str) -> dict:
        event_id, responses = await nostr.send_dm(recipient_pubkey, plaintext)
        return {
            "event_id": event_id,
            "relays": [r.model_dump(mode="json") for r in responses],
        }

    server.register_tool(
        "nostr_broadcast",
        "Sign and broadcast a Nostr event to multiple relays. Use for: publish proof-of-work, announce reputation, share public data.",
        {
            "type": "object",
            "properties": {
                "kind": {"type": "integer", "description": "Nostr event kind (1=text note, 30023=long-form, etc)."},
                "content": {"type": "string", "description": "Event content."},
                "tags": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "string"}},
                    "description": "NIP-01 tags as list of string arrays.",
                },
                "pow_target": {
                    "type": ["integer", "null"],
                    "description": "NIP-13 leading-zero bits target; omit or null to skip PoW.",
                },
            },
            "required": ["kind", "content"],
            "additionalProperties": False,
        },
        nostr_broadcast,
    )
    server.register_tool(
        "nostr_encrypt_dm",
        "Send an encrypted direct message to a Nostr pubkey (NIP-17 gift-wrapped, NIP-44 encrypted).",
        {
            "type": "object",
            "properties": {
                "recipient_pubkey": {"type": "string", "description": "Hex-encoded 32-byte secp256k1 x-only pubkey."},
                "plaintext": {"type": "string", "description": "Message body to encrypt."},
            },
            "required": ["recipient_pubkey", "plaintext"],
            "additionalProperties": False,
        },
        nostr_encrypt_dm,
    )


# ------------------------------------------------------------ lightning tools


def register_lightning_tools(server: "MCPServer", wallet: "LightningWallet") -> None:
    async def lightning_balance() -> dict:
        sats = await wallet.get_balance()
        return {"balance_sats": int(sats)}

    async def lightning_create_invoice(amount_sats: int, memo: str = "") -> dict:
        bolt11 = await wallet.create_invoice(int(amount_sats), memo)
        return {"bolt11": bolt11}

    async def lightning_pay(bolt11: str) -> dict:
        result = await wallet.pay_invoice(bolt11)
        return result.model_dump(mode="json")

    server.register_tool(
        "lightning_balance",
        "Check the current Lightning wallet balance in satoshis.",
        {"type": "object", "properties": {}, "additionalProperties": False},
        lightning_balance,
    )
    server.register_tool(
        "lightning_create_invoice",
        "Create a Lightning invoice to receive payment.",
        {
            "type": "object",
            "properties": {
                "amount_sats": {"type": "integer", "minimum": 1, "description": "Amount in satoshis."},
                "memo": {"type": "string", "description": "Description shown to the payer."},
            },
            "required": ["amount_sats"],
            "additionalProperties": False,
        },
        lightning_create_invoice,
    )
    server.register_tool(
        "lightning_pay",
        "Pay a Lightning invoice. Rejects if amount exceeds per-task or daily spend limits.",
        {
            "type": "object",
            "properties": {
                "bolt11": {"type": "string", "description": "BOLT11 invoice string."},
            },
            "required": ["bolt11"],
            "additionalProperties": False,
        },
        lightning_pay,
    )
