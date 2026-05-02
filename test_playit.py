#!/usr/bin/env python3
"""
Test function for PlayIT tunnel creation and deletion.
Tests basic tunnel lifecycle with hardcoded values.

Usage:
    python test_playit.py
"""

import asyncio
from playit_manager import create_tunnel, delete_tunnel
from logger import get_logger

log = get_logger("test_playit")

TUNNEL_NAME = "test-tunnel-minecraft2"
TUNNEL_PORT = 25565


async def test_playit_tunnel():
    """Create a tunnel, then delete it."""
    log.info("=== Starting PlayIT tunnel test ===")

    # Test creation
    log.info("Creating tunnel: name=%s, port=%d", TUNNEL_NAME, TUNNEL_PORT)
    address = await create_tunnel(TUNNEL_NAME, TUNNEL_PORT)

    if not address:
        log.error("Tunnel creation failed")
        return False

    log.info("✓ Tunnel created successfully: %s", address)

    # Test deletion
    log.info("Deleting tunnel: %s", TUNNEL_NAME)
    deleted = await delete_tunnel(TUNNEL_NAME)

    if not deleted:
        log.error("Tunnel deletion failed")
        return False

    log.info("✓ Tunnel deleted successfully")
    log.info("=== PlayIT tunnel test passed ===")
    return True


if __name__ == "__main__":
    result = asyncio.run(test_playit_tunnel())
    exit(0 if result else 1)
