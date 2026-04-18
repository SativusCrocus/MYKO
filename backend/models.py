"""Pydantic v2 models shared across the Nostr and broadcast layers."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UnsignedEvent(BaseModel):
    """NIP-01 event prior to signing.

    ``serialize()`` produces the canonical JSON array used for event-id hashing:
    ``[0, pubkey, created_at, kind, tags, content]`` with no extra whitespace.
    """

    model_config = ConfigDict(extra="forbid")

    pubkey: str
    created_at: int
    kind: int
    tags: list[list[str]] = Field(default_factory=list)
    content: str

    def serialize(self) -> str:
        array: list[Any] = [0, self.pubkey, self.created_at, self.kind, self.tags, self.content]
        return json.dumps(array, separators=(",", ":"), ensure_ascii=False)


class SignedEvent(UnsignedEvent):
    id: str
    sig: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pubkey": self.pubkey,
            "created_at": self.created_at,
            "kind": self.kind,
            "tags": self.tags,
            "content": self.content,
            "sig": self.sig,
        }


class RelayResponse(BaseModel):
    relay_url: str
    accepted: bool
    message: str = ""
