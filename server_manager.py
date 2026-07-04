"""
Core server provisioning and deprovisioning logic.

This module is the single source of truth for all server lifecycle operations.
It is consumed by both the Flask API (app.py) and the CLI scripts
(main.py, delete_server.py).

Provisioning sequence:
    1. Insert the server record into the local SQLite database.
    2. Create and start the Minecraft server container via docker_manager.
    3. Create a PlayIT tunnel for the server's local port.
    4. Resolve the tunnel's external port via DNS SRV lookup.
    5. Create a Cloudflare CNAME record pointing the subdomain to the tunnel.
    6. Create a Cloudflare SRV record so Minecraft clients discover the port.

Deprovisioning sequence:
    1. Retrieve the server record and linked resources from the database.
    2. Stop and remove the server's container; delete its data directory.
    3. Delete all Cloudflare DNS records by their stored record IDs and any
       PlayIT tunnels.
    4. Delete the database row, which cascades to playit_tunnels, dns_records,
       backups, and backup_schedules.
"""

import asyncio
import re
import secrets
import shutil
import sqlite3

from dotenv import load_dotenv

import docker_manager
from docker_manager import SERVER_TYPES, server_data_dir
from db import get_db
from playit_manager import create_tunnel, delete_tunnel
from cloudflare_manager import (
    create_dns_record,
    create_srv_record,
    lookup_minecraft_srv_port,
    delete_dns_record_by_id,
)
from logger import get_logger

load_dotenv()

log = get_logger("server_manager")


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "server"


def provision_server(
    server_name: str,
    server_type: str = "paper",
    version: str = "1.21.4",
    server_port: int = 25565,
    mem_min: int = 2,
    mem_max: int = 4,
    subscription: str | None = None,
    agent: str | None = None,
) -> dict:
    """Provision a complete Minecraft server stack.

    Creates a Docker container running the Minecraft server, a PlayIT tunnel,
    and the required Cloudflare DNS records in sequence. Each step's result
    is persisted to the database.

    Args:
        server_name: Display name for the server.
        server_type: One of the keys in SERVER_TYPES (e.g. "paper", "forge").
        version:     Minecraft version string (e.g. "1.21.4").
        server_port: Host TCP port the game server is published on.
        mem_min:     Minimum JVM heap size in GB.
        mem_max:     Maximum JVM heap size in GB.
        subscription: Network subscription level: "premium" or "free".
                    Defaults to PLAYIT_SUBSCRIPTION env var or "premium".
        agent: Agent name for the tunnel (e.g., "US-East", "EU-Central").
               Defaults to PLAYIT_AGENT env var or first available agent.

    Returns:
        A dict containing ``success`` (bool) and ``message`` (str).
        On success, also includes ``server_id``, ``connect_address``,
        ``tunnel_address``, and ``external_port``.
    """
    if server_type not in SERVER_TYPES:
        return {
            "success": False,
            "message": f"Unknown server type '{server_type}'. Valid types: {list(SERVER_TYPES)}",
        }

    subdomain = _slugify(server_name)
    log.info(
        "Provisioning server: name=%s, type=%s, version=%s, port=%d",
        server_name, server_type, version, server_port,
    )

    # Step 1: Persist server record
    rcon_password = secrets.token_urlsafe(24)
    db_server_id = None
    try:
        with get_db() as conn:
            cur = conn.execute(
                "INSERT INTO servers"
                " (name, slug, type, version, serverport, mem_min_gb, mem_max_gb, rcon_password, status)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'provisioning')",
                (server_name, subdomain, server_type, version, server_port, mem_min, mem_max, rcon_password),
            )
            db_server_id = cur.lastrowid
        log.info("Server record persisted: db_id=%d", db_server_id)
    except sqlite3.IntegrityError as exc:
        log.warning("Server creation conflict: %s", exc)
        return {"success": False, "message": f"Port {server_port} is already in use by another server", "conflict": True}
    except sqlite3.Error as exc:
        log.error("Database error while persisting server record: %s", exc)
        return {"success": False, "message": f"Database error: {exc}"}

    # Step 2: Create and start the Minecraft server container
    try:
        with get_db() as conn:
            row = conn.execute("SELECT * FROM servers WHERE id = ?", (db_server_id,)).fetchone()
        container_id = docker_manager.create_server_container(row)
        with get_db() as conn:
            conn.execute(
                "UPDATE servers SET container_id = ?, status = 'created' WHERE id = ?",
                (container_id, db_server_id),
            )
    except Exception as exc:
        log.error("Container creation failed for db_id=%d: %s", db_server_id, exc)
        with get_db() as conn:
            conn.execute("UPDATE servers SET status = 'error' WHERE id = ?", (db_server_id,))
        return {"success": False, "message": f"Container creation failed: {exc}", "server_id": db_server_id}

    # Step 3: Create PlayIT tunnel
    log.info("Creating PlayIT tunnel: name=%s, local_port=%d", subdomain, server_port)
    tunnel_address = asyncio.run(create_tunnel(tunnel_name=subdomain, tunnel_port=server_port, subscription=subscription, agent=agent))
    if not tunnel_address:
        log.error("PlayIT tunnel creation failed for server db_id=%d", db_server_id)
        return {"success": False, "message": "PlayIT tunnel creation failed", "server_id": db_server_id}

    # Resolve external port via SRV lookup
    external_port = lookup_minecraft_srv_port(tunnel_address)
    if external_port:
        log.debug("External port resolved: %d", external_port)
    else:
        log.warning("Could not resolve external port for tunnel %s", tunnel_address)

    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO playit_tunnels"
                " (server_id, tunnel_name, tunnel_address, local_port, external_port)"
                " VALUES (?, ?, ?, ?, ?)",
                (db_server_id, subdomain, tunnel_address, server_port, external_port),
            )
        log.debug("Tunnel record persisted: address=%s", tunnel_address)
    except sqlite3.Error as exc:
        log.warning("Failed to persist tunnel record: %s", exc)

    # Step 5: Create Cloudflare CNAME record
    log.info("Creating Cloudflare CNAME: %s -> %s", subdomain, tunnel_address)
    cname_result = create_dns_record(subdomain=subdomain, target=tunnel_address)
    if not cname_result:
        log.error("Cloudflare CNAME creation failed for subdomain=%s", subdomain)
        return {"success": False, "message": "Cloudflare CNAME creation failed", "tunnel_address": tunnel_address}

    dns_name, cname_cf_id = cname_result

    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO dns_records"
                " (server_id, record_type, name, target, cloudflare_record_id)"
                " VALUES (?, ?, ?, ?, ?)",
                (db_server_id, "CNAME", dns_name, tunnel_address, cname_cf_id),
            )
        log.debug("CNAME record persisted: name=%s, cf_id=%s", dns_name, cname_cf_id)
    except sqlite3.Error as exc:
        log.warning("Failed to persist CNAME record: %s", exc)

    # Step 6: Create Cloudflare SRV record
    if external_port:
        log.info("Creating Cloudflare SRV record: port=%d", external_port)
        srv_cf_id = create_srv_record(subdomain=subdomain, target=tunnel_address, port=external_port)
        if srv_cf_id:
            srv_name = f"_minecraft._tcp.{dns_name}"
            try:
                with get_db() as conn:
                    conn.execute(
                        "INSERT INTO dns_records"
                        " (server_id, record_type, name, target, port, cloudflare_record_id)"
                        " VALUES (?, ?, ?, ?, ?, ?)",
                        (db_server_id, "SRV", srv_name, tunnel_address, external_port, srv_cf_id),
                    )
                log.debug("SRV record persisted: name=%s, cf_id=%s", srv_name, srv_cf_id)
            except sqlite3.Error as exc:
                log.warning("Failed to persist SRV record: %s", exc)

    log.info(
        "Server provisioned successfully: db_id=%d, connect_address=%s",
        db_server_id, dns_name,
    )
    return {
        "success": True,
        "message": "Server provisioned successfully",
        "server_id": db_server_id,
        "connect_address": dns_name,
        "tunnel_address": tunnel_address,
        "external_port": external_port,
    }


def deprovision_server(db_server_id: int) -> dict:
    """Remove a server and all associated resources.

    Stops/removes the server's container, deletes its data directory, all
    Cloudflare DNS records and PlayIT tunnels, and the database row (which
    cascades to playit_tunnels, dns_records, backups, backup_schedules).

    Args:
        db_server_id: The primary key of the server in the ``servers`` table.

    Returns:
        A dict containing ``success`` (bool) and ``message`` (str).
    """
    log.info("Deprovisioning server: db_id=%d", db_server_id)

    try:
        with get_db() as conn:
            row = conn.execute("SELECT id, name FROM servers WHERE id = ?", (db_server_id,)).fetchone()
            if not row:
                return {"success": False, "message": f"No server found with ID {db_server_id}"}
            server_name = row["name"]

            dns_rows = conn.execute(
                "SELECT cloudflare_record_id, name FROM dns_records WHERE server_id = ?",
                (db_server_id,),
            ).fetchall()
            tunnel_rows = conn.execute(
                "SELECT tunnel_name FROM playit_tunnels WHERE server_id = ?",
                (db_server_id,),
            ).fetchall()
    except sqlite3.Error as exc:
        log.error("Database error while fetching server record: %s", exc)
        return {"success": False, "message": f"Database error: {exc}"}

    # Stop and remove the container
    try:
        docker_manager.remove_server(db_server_id)
    except Exception as exc:
        log.warning("Error removing container for db_id=%d: %s", db_server_id, exc)

    # Delete the server's data directory
    data_dir = server_data_dir(db_server_id)
    base = docker_manager.SERVERS_DIR
    if data_dir.startswith(base):
        shutil.rmtree(data_dir, ignore_errors=True)
    else:
        log.warning("Refusing to delete data dir outside SERVERS_DIR: %s", data_dir)

    # Delete PlayIT tunnels
    for row in tunnel_rows:
        tunnel_name = row["tunnel_name"]
        log.info("Deleting PlayIT tunnel: name=%s", tunnel_name)
        success = asyncio.run(delete_tunnel(tunnel_name))
        if not success:
            log.warning("Could not delete PlayIT tunnel '%s' — may need manual removal", tunnel_name)

    # Delete Cloudflare DNS records
    for row in dns_rows:
        log.info("Deleting Cloudflare record: name=%s, cf_id=%s", row["name"], row["cloudflare_record_id"])
        delete_dns_record_by_id(row["cloudflare_record_id"])

    # Delete database row (cascades to playit_tunnels, dns_records, backups, backup_schedules)
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM servers WHERE id = ?", (db_server_id,))
        log.info(
            "Server deprovisioned: db_id=%d, name=%s (tunnel, DNS, backup records cascaded)",
            db_server_id, server_name,
        )
    except sqlite3.Error as exc:
        log.error("Database error during server deletion: %s", exc)
        return {"success": False, "message": f"Database error during deletion: {exc}"}

    return {"success": True, "message": f"Server '{server_name}' deleted successfully"}


def list_servers() -> list[dict]:
    """Return all servers with their associated tunnels, DNS records, and runtime status.

    Returns:
        A list of server dicts.  Each dict includes ``id``, ``name``,
        ``type``, ``version``, ``port``, ``status``, ``runtime_status``,
        ``created_at``, ``tunnels``, and ``dns_records``.
    """
    try:
        with get_db() as conn:
            servers = conn.execute(
                "SELECT id, name, slug, type, version, serverport, mem_min_gb, mem_max_gb, status, createdat"
                " FROM servers ORDER BY id"
            ).fetchall()
            result = []
            for s in servers:
                tunnels = conn.execute(
                    "SELECT tunnel_address, local_port, external_port"
                    " FROM playit_tunnels WHERE server_id = ?",
                    (s["id"],),
                ).fetchall()
                dns = conn.execute(
                    "SELECT record_type, name, target, port"
                    " FROM dns_records WHERE server_id = ?",
                    (s["id"],),
                ).fetchall()
                result.append({
                    "id": s["id"],
                    "name": s["name"],
                    "slug": s["slug"],
                    "type": s["type"],
                    "version": s["version"],
                    "port": s["serverport"],
                    "mem_min": s["mem_min_gb"],
                    "mem_max": s["mem_max_gb"],
                    "status": s["status"],
                    "runtime_status": docker_manager.runtime_status(s["id"]),
                    "created_at": s["createdat"],
                    "tunnels": [
                        {"address": t["tunnel_address"], "local_port": t["local_port"], "external_port": t["external_port"]}
                        for t in tunnels
                    ],
                    "dns_records": [
                        {"type": d["record_type"], "name": d["name"], "target": d["target"], "port": d["port"]}
                        for d in dns
                    ],
                })
        log.debug("Listed %d servers", len(result))
        return result
    except sqlite3.Error as exc:
        log.error("Database error while listing servers: %s", exc)
        return []


def create_server_tunnel(db_server_id: int, region: str | None = None, subscription: str | None = None, agent: str | None = None) -> dict:
    """Create a PlayIT tunnel and Cloudflare DNS records for an existing server.

    Args:
        db_server_id: Database ID of the server.
        region: Optional server region (e.g., "Germany", "Seattle", "Japan").
                Defaults to PLAYIT_REGION env var.
        subscription: Optional network subscription level: "premium" or "free".
                    Defaults to PLAYIT_SUBSCRIPTION env var or "premium".
        agent: Optional agent name for the tunnel (e.g., "US-East", "EU-Central").
               Defaults to PLAYIT_AGENT env var or first available agent.
    """
    try:
        with get_db() as conn:
            row = conn.execute("SELECT name, serverport FROM servers WHERE id = ?", (db_server_id,)).fetchone()
    except sqlite3.Error as exc:
        log.error("Database error fetching server %d: %s", db_server_id, exc)
        return {"success": False, "message": f"Database error: {exc}"}

    if not row:
        return {"success": False, "message": f"No server found with ID {db_server_id}"}

    server_name, server_port = row["name"], row["serverport"]
    subdomain = _slugify(server_name)

    log.info("Creating PlayIT tunnel: name=%s, local_port=%d, region=%s", subdomain, server_port, region or "default")
    tunnel_address = asyncio.run(create_tunnel(tunnel_name=subdomain, tunnel_port=server_port, region=region, subscription=subscription, agent=agent))
    if not tunnel_address:
        return {"success": False, "message": "PlayIT tunnel creation failed"}

    external_port = lookup_minecraft_srv_port(tunnel_address)
    if external_port:
        log.debug("External port resolved: %d", external_port)
    else:
        log.warning("Could not resolve external port for tunnel %s", tunnel_address)

    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO playit_tunnels"
                " (server_id, tunnel_name, tunnel_address, local_port, external_port)"
                " VALUES (?, ?, ?, ?, ?)",
                (db_server_id, subdomain, tunnel_address, server_port, external_port),
            )
    except sqlite3.Error as exc:
        log.warning("Failed to persist tunnel record: %s", exc)

    log.info("Creating Cloudflare CNAME: %s -> %s", subdomain, tunnel_address)
    cname_result = create_dns_record(subdomain=subdomain, target=tunnel_address)
    if not cname_result:
        return {
            "success": False,
            "message": "Cloudflare CNAME creation failed",
            "tunnel_address": tunnel_address,
            "external_port": external_port,
        }

    dns_name, cname_cf_id = cname_result

    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO dns_records"
                " (server_id, record_type, name, target, cloudflare_record_id)"
                " VALUES (?, ?, ?, ?, ?)",
                (db_server_id, "CNAME", dns_name, tunnel_address, cname_cf_id),
            )
    except sqlite3.Error as exc:
        log.warning("Failed to persist CNAME record: %s", exc)

    if external_port:
        srv_cf_id = create_srv_record(subdomain=subdomain, target=tunnel_address, port=external_port)
        if srv_cf_id:
            srv_name = f"_minecraft._tcp.{dns_name}"
            try:
                with get_db() as conn:
                    conn.execute(
                        "INSERT INTO dns_records"
                        " (server_id, record_type, name, target, port, cloudflare_record_id)"
                        " VALUES (?, ?, ?, ?, ?, ?)",
                        (db_server_id, "SRV", srv_name, tunnel_address, external_port, srv_cf_id),
                    )
            except sqlite3.Error as exc:
                log.warning("Failed to persist SRV record: %s", exc)

    log.info(
        "Tunnel created for server db_id=%d: connect_address=%s, external_port=%s",
        db_server_id, dns_name, external_port,
    )
    return {
        "success": True,
        "message": "Tunnel and DNS records created successfully",
        "tunnel_address": tunnel_address,
        "external_port": external_port,
        "connect_address": dns_name,
    }


def rename_server_subdomain(db_server_id: int, new_subdomain: str) -> dict:
    """Delete old Cloudflare DNS records and create new ones under a new subdomain."""
    try:
        with get_db() as conn:
            if not conn.execute("SELECT id FROM servers WHERE id = ?", (db_server_id,)).fetchone():
                return {"success": False, "message": f"No server found with ID {db_server_id}"}
            old_dns_rows = conn.execute(
                "SELECT cloudflare_record_id, record_type, name"
                " FROM dns_records WHERE server_id = ?",
                (db_server_id,),
            ).fetchall()
            tunnel_row = conn.execute(
                "SELECT tunnel_address, external_port FROM playit_tunnels WHERE server_id = ?",
                (db_server_id,),
            ).fetchone()
    except sqlite3.Error as exc:
        log.error("Database error fetching server %d: %s", db_server_id, exc)
        return {"success": False, "message": f"Database error: {exc}"}

    if not tunnel_row:
        return {"success": False, "message": "No tunnel found for this server — create one first"}

    tunnel_address, external_port = tunnel_row["tunnel_address"], tunnel_row["external_port"]

    for row in old_dns_rows:
        log.info("Deleting old DNS record: type=%s name=%s cf_id=%s", row["record_type"], row["name"], row["cloudflare_record_id"])
        delete_dns_record_by_id(row["cloudflare_record_id"])

    try:
        with get_db() as conn:
            conn.execute("DELETE FROM dns_records WHERE server_id = ?", (db_server_id,))
    except sqlite3.Error as exc:
        log.warning("Failed to delete old DNS records from DB: %s", exc)

    log.info("Creating Cloudflare CNAME: %s -> %s", new_subdomain, tunnel_address)
    cname_result = create_dns_record(subdomain=new_subdomain, target=tunnel_address)
    if not cname_result:
        return {"success": False, "message": "Cloudflare CNAME creation failed"}

    dns_name, cname_cf_id = cname_result

    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO dns_records"
                " (server_id, record_type, name, target, cloudflare_record_id)"
                " VALUES (?, ?, ?, ?, ?)",
                (db_server_id, "CNAME", dns_name, tunnel_address, cname_cf_id),
            )
    except sqlite3.Error as exc:
        log.warning("Failed to persist new CNAME record: %s", exc)

    if external_port:
        srv_cf_id = create_srv_record(subdomain=new_subdomain, target=tunnel_address, port=external_port)
        if srv_cf_id:
            srv_name = f"_minecraft._tcp.{dns_name}"
            try:
                with get_db() as conn:
                    conn.execute(
                        "INSERT INTO dns_records"
                        " (server_id, record_type, name, target, port, cloudflare_record_id)"
                        " VALUES (?, ?, ?, ?, ?, ?)",
                        (db_server_id, "SRV", srv_name, tunnel_address, external_port, srv_cf_id),
                    )
            except sqlite3.Error as exc:
                log.warning("Failed to persist new SRV record: %s", exc)

    try:
        with get_db() as conn:
            conn.execute(
                "UPDATE playit_tunnels SET tunnel_name = ? WHERE server_id = ?",
                (new_subdomain, db_server_id),
            )
    except sqlite3.Error as exc:
        log.warning("Failed to update tunnel_name: %s", exc)

    log.info(
        "Subdomain renamed for server db_id=%d: new connect_address=%s",
        db_server_id, dns_name,
    )
    return {
        "success": True,
        "message": "Subdomain renamed successfully",
        "connect_address": dns_name,
    }
