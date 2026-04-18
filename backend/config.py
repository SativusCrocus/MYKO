"""Pydantic Settings v2 — all runtime configuration loaded from environment / .env."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    MYKO_PASSPHRASE: str = Field(min_length=8)
    MYKO_HOME: Path = Field(default_factory=lambda: Path.home() / "MYKO")
    IPFS_API_URL: str = "http://127.0.0.1:5001/api/v0"

    NOSTR_RELAYS: list[str] = Field(
        default_factory=lambda: [
            "wss://relay.damus.io",
            "wss://nos.lol",
            "wss://relay.nostr.band",
        ]
    )
    NOSTR_KEY_FILENAME: str = "nostr_privkey"

    LIGHTNING_BACKEND: Literal["lnd", "lnbits"] = "lnbits"
    LIGHTNING_URL: str = "https://127.0.0.1:8080"
    LIGHTNING_MACAROON_PATH: Path | None = None
    LIGHTNING_API_KEY: str | None = None
    LIGHTNING_TLS_CERT_PATH: Path | None = None

    MAX_SATS_PER_TASK: int = 1000
    MAX_DAILY_SATS: int = 10000

    LOG_LEVEL: str = "INFO"
    BRIDGE_PORT: int = 9473
    YUBIKEY_ENABLED: bool = False

    @field_validator("MYKO_HOME", mode="before")
    @classmethod
    def _expand_home(cls, v):
        if isinstance(v, str):
            return Path(v).expanduser()
        if isinstance(v, Path):
            return v.expanduser()
        return v

    @field_validator("NOSTR_RELAYS", mode="before")
    @classmethod
    def _parse_relays(cls, v):
        if isinstance(v, str):
            import json

            stripped = v.strip()
            if stripped.startswith("["):
                return json.loads(stripped)
            return [r.strip() for r in stripped.split(",") if r.strip()]
        return v
