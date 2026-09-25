#!/usr/bin/env python3
"""
Interactive CLI for deprovisioning a server by its database ID.

Delegates to server_manager.deprovision_server(), which stops/removes the
server's container, deletes its data directory, removes the PlayIT tunnel
and deletes the database row (cascading to
linked tunnels and backups).

Usage:
    python delete_server.py <db_server_id>
    python delete_server.py          # prompts interactively
"""

import sys

from db import get_db
from server_manager import deprovision_server
from logger import get_logger

log = get_logger("delete_server")


def _print_summary(db_server_id: int) -> bool:
    """Print server details for confirmation. Returns False if not found."""
    with get_db() as conn:
        row = conn.execute("SELECT id, name, slug, serverport FROM servers WHERE id = ?", (db_server_id,)).fetchone()
        if not row:
            log.error("No server found with database ID %d", db_server_id)
            return False

        tunnels = conn.execute(
            "SELECT tunnel_address, local_port, external_port FROM playit_tunnels WHERE server_id = ?",
            (db_server_id,),
        ).fetchall()

    print()
    print(f"  Server ID   : {row['id']}")
    print(f"  Name        : {row['name']}")
    print(f"  Tunnel name : {row['slug']}")
    print(f"  Port        : {row['serverport']}")
    for t in tunnels:
        print(f"  Tunnel      : {t['tunnel_address']}  local={t['local_port']}  external={t['external_port']}")
    print()
    return True


def delete_server(db_server_id: int) -> None:
    """Deprovision a server interactively, after displaying a confirmation summary."""
    if not _print_summary(db_server_id):
        return

    confirm = input("Permanently delete this server and all its resources? [y/N] ").strip().lower()
    if confirm != "y":
        print("Operation cancelled.")
        return

    result = deprovision_server(db_server_id)
    if result["success"]:
        print(f"\n{result['message']}\n")
    else:
        log.error("Deprovisioning failed: %s", result["message"])
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) == 2:
        raw_id = sys.argv[1]
    else:
        raw_id = input("Database server ID to delete: ").strip()

    if not raw_id.isdigit():
        log.error("Invalid server ID '%s' — must be a positive integer", raw_id)
        sys.exit(1)

    delete_server(int(raw_id))
