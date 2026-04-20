"""MCP entry point. Spawned by Goose as: ``python -m backend.main``.

Boots logging → backend instances → MCP server → stdio loop.

Phases 2/3 extend this to register Nostr and Lightning tool bundles. Their
imports are wrapped in try/except so a partial install (Phase 1 only, no
``coincurve`` / ``bolt11``) still produces a working vault-only server.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from .config import Settings
from .crypto import KeyManager
from .logging_config import configure_logging
from .mcp_server import MCPServer
from .mcp_tools import register_vault_tools
from .storage import StorageEngine
from .vault import VaultManager


async def _run() -> None:
    settings = Settings()
    log = configure_logging(settings.MYKO_HOME, settings.LOG_LEVEL)
    log.info("Booting MYKO MCP server", extra={"action": "boot"})

    key_mgr = KeyManager(settings.MYKO_PASSPHRASE, yubikey_enabled=settings.YUBIKEY_ENABLED)

    async with StorageEngine(settings.IPFS_API_URL) as storage:
        vault = VaultManager(key_mgr, storage, settings.MYKO_HOME)
        server = MCPServer(status_path=settings.MYKO_HOME / ".goose_status.json")

        register_vault_tools(server, vault, storage)

        # Optional: Nostr identity (Phase 2).
        try:
            from .mcp_tools import register_nostr_tools
            from .nostr import NostrClient

            nostr = NostrClient(vault, settings)
            register_nostr_tools(server, nostr)
            log.info("Registered Nostr tools")
        except ImportError as e:
            log.warning(f"Nostr tools not available: {e}")

        # Optional: Lightning payments (Phase 3).
        wallet = None
        try:
            from .lightning import LightningWallet
            from .mcp_tools import register_lightning_tools

            wallet = LightningWallet.create(settings)
            await wallet.__aenter__()
            register_lightning_tools(server, wallet)
            log.info("Registered Lightning tools")
        except ImportError as e:
            log.warning(f"Lightning tools not available: {e}")

        try:
            await server.run()
        finally:
            if wallet is not None:
                await wallet.close()


def main() -> None:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"FATAL: {type(e).__name__}: {e}", file=sys.stderr)
        logging.getLogger("myko").exception("Fatal error during startup")
        sys.exit(1)


if __name__ == "__main__":
    main()
