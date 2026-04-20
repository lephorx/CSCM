#!/usr/bin/env python3
"""
Interactive CLI for deprovisioning a server by its database ID.

Deprovisioning sequence:
    1. Fetch the server record and all linked resources from the database.
    2. Display a summary and prompt for confirmation.
    3. Delete the Crafty game server.
    4. Delete all Cloudflare DNS records using their stored record IDs.
    5. Delete the database row (cascades to playit_tunnels and dns_records).

Usage:
    python delete_server.py <db_server_id>
    python delete_server.py          # prompts interactively
"""

import os
import sys
import requests
import urllib3
import psycopg2
from dotenv import load_dotenv

from cloudflare_manager import delete_dns_record_by_id
from logger import get_logger

load_dotenv()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = get_logger("delete_server")

# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------
try:
    connection = psycopg2.connect(
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        sslmode="require",
    )
    cursor = connection.cursor()
except psycopg2.OperationalError as exc:
    log.error("Database connection failed: %s", exc)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Crafty Controller configuration
# ---------------------------------------------------------------------------
base_url        = os.getenv("BASE_URL", "https://localhost:8443")
crafty_username = os.getenv("USERNAME", "admin")
crafty_password = os.getenv("PASSWORD", "admin")


def crafty_login() -> str | None:
    """Authenticate with Crafty Controller and return a bearer token."""
    try:
        r = requests.post(
            f"{base_url}/api/v2/auth/login",
            json={"username": crafty_username, "password": crafty_password},
            verify=False,
        )
        if r.status_code == 200:
            return r.json()["data"]["token"]
        log.error("Crafty authentication failed: HTTP %d", r.status_code)
        return None
    except requests.exceptions.ConnectionError:
        log.error("Cannot reach Crafty Controller at %s", base_url)
        return None


def _delete_crafty_server(crafty_server_id: str, headers: dict) -> None:
    """Send a DELETE request to Crafty for the given server ID."""
    try:
        r = requests.delete(
            f"{base_url}/api/v2/servers/{crafty_server_id}",
            headers=headers,
            verify=False,
        )
        if r.ok:
            log.info("Crafty server deleted: crafty_id=%s", crafty_server_id)
        else:
            log.warning(
                "Crafty deletion returned HTTP %d for crafty_id=%s: %s",
                r.status_code, crafty_server_id, r.text,
            )
    except requests.exceptions.RequestException as exc:
        log.error("Error deleting Crafty server: %s", exc)


def delete_server(db_server_id: int) -> None:
    """Deprovision a server interactively.

    Fetches all linked resources, prompts for confirmation, then
    removes the Crafty server, Cloudflare DNS records, and the
    database entry.
    """
    # Fetch server record
    cursor.execute(
        "SELECT id, name, craftyid FROM servers WHERE id = %s",
        (db_server_id,),
    )
    row = cursor.fetchone()
    if not row:
        log.error("No server found with database ID %d", db_server_id)
        return

    db_id, server_name, crafty_server_id = row
    subdomain = server_name.lower().replace(" ", "-")

    # Fetch linked DNS records
    cursor.execute(
        "SELECT record_type, name, target, port, cloudflare_record_id"
        " FROM dns_records WHERE server_id = %s",
        (db_server_id,),
    )
    dns_rows = cursor.fetchall()

    # Fetch linked PlayIT tunnels
    cursor.execute(
        "SELECT tunnel_name, tunnel_address, local_port, external_port"
        " FROM playit_tunnels WHERE server_id = %s",
        (db_server_id,),
    )
    tunnel_rows = cursor.fetchall()

    # Display summary
    print()
    print(f"  Server ID   : {db_id}")
    print(f"  Name        : {server_name}")
    print(f"  Subdomain   : {subdomain}")
    print(f"  Crafty ID   : {crafty_server_id or '(none)'}")
    for t in tunnel_rows:
        print(f"  Tunnel      : {t[1]}  local={t[2]}  external={t[3]}")
    for d in dns_rows:
        port_suffix = f":{d[3]}" if d[3] else ""
        print(f"  DNS [{d[0]:5}] : {d[1]} -> {d[2]}{port_suffix}")
    print()

    confirm = input("Permanently delete this server and all its resources? [y/N] ").strip().lower()
    if confirm != "y":
        print("Operation cancelled.")
        return

    # Step 1: Delete Crafty server
    print()
    log.info("[1/3] Deleting Crafty server")
    if crafty_server_id:
        token = crafty_login()
        if token:
            _delete_crafty_server(crafty_server_id, {"Authorization": f"Bearer {token}"})
        else:
            log.warning("Skipping Crafty deletion — authentication failed")
    else:
        log.debug("No Crafty ID on record, skipping Crafty deletion")

    # Step 2: Delete Cloudflare DNS records
    log.info("[2/3] Deleting Cloudflare DNS records")
    if dns_rows:
        for _, name, _, _, cf_id in dns_rows:
            log.debug("Deleting record: name=%s, cf_id=%s", name, cf_id)
            delete_dns_record_by_id(cf_id)
    else:
        log.debug("No DNS records on record for db_id=%d", db_server_id)

    # Step 3: Delete database entry
    log.info("[3/3] Deleting database entry")
    try:
        cursor.execute("DELETE FROM servers WHERE id = %s", (db_server_id,))
        connection.commit()
        log.info(
            "Server deprovisioned: db_id=%d, name=%s (tunnel + DNS records cascaded)",
            db_server_id, server_name,
        )
    except psycopg2.Error as exc:
        log.error("Database error during deletion: %s", exc)
        connection.rollback()
        return

    print(f"\nServer '{server_name}' has been fully deleted.\n")


if __name__ == "__main__":
    if len(sys.argv) == 2:
        raw_id = sys.argv[1]
    else:
        raw_id = input("Database server ID to delete: ").strip()

    if not raw_id.isdigit():
        log.error("Invalid server ID '%s' — must be a positive integer", raw_id)
        sys.exit(1)

    delete_server(int(raw_id))
