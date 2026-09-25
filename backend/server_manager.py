"""
Core server provisioning and deprovisioning logic.

This module is the single source of truth for all server lifecycle operations.
It is consumed by both the Flask API (app.py) and the CLI scripts
(main.py, delete_server.py).

Provisioning sequence:
    1. Insert the server record into the local SQLite database.
    2. Create and start the Minecraft server container via docker_manager.
    3. Create a PlayIT tunnel for the server's local port.
    4. Resolve the PlayIT tunnel's external port for display.
    5. Create Cloudflare DNS records when configured.

Deprovisioning sequence:
    1. Retrieve the server record and linked resources from the database.
    2. Stop and remove the server's container; delete its data directory.
    3. Delete the PlayIT tunnels and any managed Cloudflare DNS records.
    4. Delete the database row and its linked records.
"""

import asyncio
import re
import secrets
import shutil
import sqlite3

from dotenv import load_dotenv

import docker_manager
import progress_store
from docker_manager import BEDROCK_TYPES, SERVER_TYPES, server_data_dir
from db import get_db
from playit_manager import create_tunnel, delete_tunnel, lookup_minecraft_srv_port
from cloudflare_manager import cloudflare_enabled, create_dns_record, create_srv_record, delete_dns_record_by_id
from logger import get_logger

load_dotenv()

log = get_logger("server_manager")


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "server"


def _split_bedrock_address(tunnel_address: str) -> tuple[str, int | None]:
    """Bedrock has no SRV-based port discovery, so playit.gg embeds the
    assigned port directly in the tunnel address as ``host:port``."""
    if tunnel_address and ":" in tunnel_address:
        host, _, port_str = tunnel_address.rpartition(":")
        if port_str.isdigit():
            return host, int(port_str)
    return tunnel_address, None


def _create_optional_dns(server_id: int, subdomain: str, tunnel_address: str,
                         external_port: int | None, is_bedrock: bool) -> tuple[str, str | None]:
    """Return the public address and any DNS warning. PlayIT always works alone."""
    if not cloudflare_enabled():
        return tunnel_address, None
    if not is_bedrock and not external_port:
        return tunnel_address, "PlayIT port lookup failed; Cloudflare DNS was skipped"

    cname = create_dns_record(subdomain=subdomain, target=tunnel_address)
    if not cname:
        return tunnel_address, "Cloudflare DNS setup failed; use the PlayIT address"
    dns_name, cname_id = cname
    srv_id = None
    if not is_bedrock:
        srv_id = create_srv_record(subdomain=subdomain, target=tunnel_address, port=external_port)
        if not srv_id:
            delete_dns_record_by_id(cname_id)
            return tunnel_address, "Cloudflare SRV setup failed; use the PlayIT address"

    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO dns_records (server_id, record_type, name, target, cloudflare_record_id)"
                " VALUES (?, 'CNAME', ?, ?, ?)",
                (server_id, dns_name, tunnel_address, cname_id),
            )
            if srv_id:
                conn.execute(
                    "INSERT INTO dns_records"
                    " (server_id, record_type, name, target, port, cloudflare_record_id)"
                    " VALUES (?, 'SRV', ?, ?, ?, ?)",
                    (server_id, f"_minecraft._tcp.{dns_name}", tunnel_address, external_port, srv_id),
                )
    except sqlite3.Error as exc:
        log.error("Could not save Cloudflare record IDs: %s", exc)
        if srv_id:
            delete_dns_record_by_id(srv_id)
        delete_dns_record_by_id(cname_id)
        return tunnel_address, "Cloudflare DNS setup could not be saved; use the PlayIT address"
    return dns_name, None


def _create_server_record(
    server_name: str,
    server_type: str,
    version: str,
    loader_version: str | None,
    server_port: int,
    mem_min: int,
    mem_max: int,
    local_only: bool = False,
) -> dict:
    """Step 1: insert the DB row and return {server_id, subdomain} or an error dict."""
    if server_type not in SERVER_TYPES:
        return {
            "success": False,
            "message": f"Unknown server type '{server_type}'. Valid types: {list(SERVER_TYPES)}",
        }

    subdomain = _slugify(server_name)
    log.info("Provisioning server: name=%s, type=%s, version=%s, port=%d, local_only=%s",
             server_name, server_type, version, server_port, local_only)

    rcon_password = secrets.token_urlsafe(24)
    try:
        with get_db() as conn:
            cur = conn.execute(
                "INSERT INTO servers"
                " (name, slug, type, version, loader_version, serverport, mem_min_gb, mem_max_gb, rcon_password, status, local_only)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'provisioning', ?)",
                (server_name, subdomain, server_type, version, loader_version,
                 server_port, mem_min, mem_max, rcon_password, int(local_only)),
            )
            db_server_id = cur.lastrowid
        log.info("Server record persisted: db_id=%d", db_server_id)
    except sqlite3.IntegrityError as exc:
        log.warning("Server creation conflict: %s", exc)
        return {"success": False, "message": f"Port {server_port} is already in use by another server", "conflict": True}
    except sqlite3.Error as exc:
        log.error("Database error while persisting server record: %s", exc)
        return {"success": False, "message": f"Database error: {exc}"}

    return {"success": True, "server_id": db_server_id, "subdomain": subdomain}


def _provision_resources(
    db_server_id: int,
    subdomain: str,
    server_port: int,
    subscription: str | None = None,
    agent: str | None = None,
) -> dict:
    """Create the Docker container, PlayIT tunnel, and optional DNS records.

    Updates progress_store throughout so GET /api/servers/<id>/progress
    can return live percentages to polling clients.
    """
    # ── Step 2: Docker container ─────────────────────────────────────────────
    progress_store.update(db_server_id, action="provision", percent=15,
                          step="Creating Docker container")
    try:
        with get_db() as conn:
            row = conn.execute("SELECT * FROM servers WHERE id = ?", (db_server_id,)).fetchone()
        server_type = row["type"]
        is_bedrock = server_type in BEDROCK_TYPES
        local_only = bool(row["local_only"])
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
        progress_store.update(db_server_id, action="provision", percent=15,
                              step="Container creation failed", status="failed", message=str(exc))
        return {"success": False, "message": f"Container creation failed: {exc}", "server_id": db_server_id}

    if local_only:
        log.info("Server db_id=%d is local-only — skipping PlayIT tunnel", db_server_id)
        progress_store.update(db_server_id, action="provision", percent=100,
                              step="Server provisioned successfully (local network only)", status="completed")
        return {
            "success": True,
            "message": "Server provisioned successfully (local network only — no public tunnel created)",
            "server_id": db_server_id,
            "local_only": True,
            "port": server_port,
            "note": "Reachable only on this machine's own network, via this host's LAN IP address and "
                    "the configured port. Call POST /api/servers/<id>/tunnel later to make it publicly "
                    "reachable if you change your mind.",
        }

    # ── Step 3: PlayIT tunnel ────────────────────────────────────────────────
    progress_store.update(db_server_id, action="provision", percent=35,
                          step="Creating PlayIT tunnel")
    log.info("Creating PlayIT tunnel: name=%s, local_port=%d, protocol=%s", subdomain, server_port, "bedrock" if is_bedrock else "java")
    tunnel_address = asyncio.run(create_tunnel(
        tunnel_name=subdomain, tunnel_port=server_port,
        subscription=subscription, agent=agent,
        protocol="bedrock" if is_bedrock else "java",
    ))
    if not tunnel_address:
        log.error("PlayIT tunnel creation failed for server db_id=%d", db_server_id)
        progress_store.update(db_server_id, action="provision", percent=35,
                              step="PlayIT tunnel creation failed", status="failed",
                              message="Could not create PlayIT tunnel")
        return {"success": False, "message": "PlayIT tunnel creation failed", "server_id": db_server_id}

    if is_bedrock:
        # No SRV-based port discovery for Bedrock — playit.gg embeds the
        # assigned port directly in the address as "host:port".
        tunnel_address, external_port = _split_bedrock_address(tunnel_address)
    else:
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

    progress_store.update(db_server_id, action="provision", percent=65,
                          step="Setting up optional Cloudflare DNS")
    connect_address, dns_warning = _create_optional_dns(
        db_server_id, subdomain, tunnel_address, external_port, is_bedrock,
    )
    log.info("Server provisioned successfully: db_id=%d, connect_address=%s", db_server_id, connect_address)
    progress_store.update(db_server_id, action="provision", percent=100,
                          step="Server provisioned successfully", status="completed",
                          message=dns_warning)
    return {
        "success": True,
        "message": "Server provisioned successfully",
        "server_id": db_server_id,
        "connect_address": connect_address,
        "tunnel_address": tunnel_address,
        "external_port": external_port,
        **({"warning": dns_warning} if dns_warning else {}),
        **({"note": "Bedrock has no SRV auto-discovery — players must enter the port manually"} if is_bedrock else {}),
    }


def provision_server(
    server_name: str,
    server_type: str = "paper",
    version: str = "1.21.4",
    loader_version: str | None = None,
    server_port: int = 25565,
    mem_min: int = 2,
    mem_max: int = 4,
    subscription: str | None = None,
    agent: str | None = None,
    local_only: bool = False,
) -> dict:
    """Synchronous wrapper used by the CLI (main.py).  The HTTP API route
    calls _create_server_record + _provision_resources directly so it can
    return a 202 with server_id before the slow steps complete.
    """
    record = _create_server_record(server_name, server_type, version, loader_version,
                                    server_port, mem_min, mem_max, local_only)
    if not record["success"]:
        return record
    return _provision_resources(record["server_id"], record["subdomain"],
                                server_port, subscription, agent)


def deprovision_server(db_server_id: int) -> dict:
    """Remove a server and all associated resources.

    Stops/removes the server's container, deletes its data directory and
    PlayIT tunnels, then deletes the database row and linked records.

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

            tunnel_rows = conn.execute(
                "SELECT tunnel_name FROM playit_tunnels WHERE server_id = ?",
                (db_server_id,),
            ).fetchall()
            dns_rows = conn.execute(
                "SELECT cloudflare_record_id FROM dns_records WHERE server_id = ?",
                (db_server_id,),
            ).fetchall()
    except sqlite3.Error as exc:
        log.error("Database error while fetching server record: %s", exc)
        return {"success": False, "message": f"Database error: {exc}"}

    # Stop and remove the container
    progress_store.update(db_server_id, action="delete", percent=10, step="Stopping container")
    try:
        docker_manager.remove_server(db_server_id)
    except Exception as exc:
        log.warning("Error removing container for db_id=%d: %s", db_server_id, exc)

    # Delete the server's data directory
    progress_store.update(db_server_id, action="delete", percent=30, step="Removing server data")
    data_dir = server_data_dir(db_server_id)
    base = docker_manager.SERVERS_DIR
    if data_dir.startswith(base):
        shutil.rmtree(data_dir, ignore_errors=True)
    else:
        log.warning("Refusing to delete data dir outside SERVERS_DIR: %s", data_dir)

    # Delete PlayIT tunnels
    progress_store.update(db_server_id, action="delete", percent=50, step="Deleting PlayIT tunnel(s)")
    for row in tunnel_rows:
        tunnel_name = row["tunnel_name"]
        log.info("Deleting PlayIT tunnel: name=%s", tunnel_name)
        success = asyncio.run(delete_tunnel(tunnel_name))
        if not success:
            log.warning("Could not delete PlayIT tunnel '%s' — may need manual removal", tunnel_name)

    if dns_rows and cloudflare_enabled():
        progress_store.update(db_server_id, action="delete", percent=75,
                              step="Removing Cloudflare DNS records")
        for row in dns_rows:
            if row["cloudflare_record_id"]:
                delete_dns_record_by_id(row["cloudflare_record_id"])
    elif dns_rows:
        log.warning("Cloudflare is disabled; existing DNS records for server %d need manual removal", db_server_id)

    # Delete database row and linked records.
    progress_store.update(db_server_id, action="delete", percent=92, step="Cleaning up database")
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM servers WHERE id = ?", (db_server_id,))
        log.info(
            "Server deprovisioned: db_id=%d, name=%s (linked records cascaded)",
            db_server_id, server_name,
        )
    except sqlite3.Error as exc:
        log.error("Database error during server deletion: %s", exc)
        return {"success": False, "message": f"Database error during deletion: {exc}"}

    progress_store.update(db_server_id, action="delete", percent=100,
                          step="Server deleted", status="completed")
    return {"success": True, "message": f"Server '{server_name}' deleted successfully"}


def list_servers() -> list[dict]:
    """Return all servers with their tunnels, DNS records, and runtime status.

    Returns:
        A list of server dicts.  Each dict includes ``id``, ``name``,
        ``type``, ``version``, ``port``, ``status``, ``runtime_status``,
        ``created_at``, ``tunnels``, and ``dns_records``.
    """
    try:
        with get_db() as conn:
            servers = conn.execute(
                "SELECT id, name, slug, type, version, loader_version, serverport, mem_min_gb, mem_max_gb, status, local_only, createdat"
                " FROM servers ORDER BY id"
            ).fetchall()
            cf_available = cloudflare_enabled()
            result = []
            for s in servers:
                tunnels = conn.execute(
                    "SELECT tunnel_address, local_port, external_port"
                    " FROM playit_tunnels WHERE server_id = ?",
                    (s["id"],),
                ).fetchall()
                dns = conn.execute(
                    "SELECT record_type, name, target, port FROM dns_records WHERE server_id = ? ORDER BY id DESC",
                    (s["id"],),
                ).fetchall()
                result.append({
                    "id": s["id"],
                    "name": s["name"],
                    "slug": s["slug"],
                    "type": s["type"],
                    "version": s["version"],
                    "loader_version": s["loader_version"],
                    "port": s["serverport"],
                    "mem_min": s["mem_min_gb"],
                    "mem_max": s["mem_max_gb"],
                    "status": s["status"],
                    "local_only": bool(s["local_only"]),
                    "cloudflare_available": cf_available,
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
    """Create a PlayIT tunnel and optional Cloudflare DNS for an existing server.

    Args:
        db_server_id: Database ID of the server.
        region: Optional server region (e.g., "Germany", "Seattle", "Japan").
                Defaults to PLAYIT_REGION env var.
        subscription: Optional network subscription level: "premium" or "free".
                    Defaults to PLAYIT_SUBSCRIPTION env var or "free".
        agent: Optional agent name for the tunnel (e.g., "US-East", "EU-Central").
               Defaults to PLAYIT_AGENT env var or first available agent.
    """
    try:
        with get_db() as conn:
            row = conn.execute("SELECT name, serverport, type FROM servers WHERE id = ?", (db_server_id,)).fetchone()
            existing = conn.execute("SELECT 1 FROM playit_tunnels WHERE server_id = ?", (db_server_id,)).fetchone()
    except sqlite3.Error as exc:
        log.error("Database error fetching server %d: %s", db_server_id, exc)
        return {"success": False, "message": f"Database error: {exc}"}

    if not row:
        return {"success": False, "message": f"No server found with ID {db_server_id}"}
    if existing:
        return {"success": False, "message": "This server already has a PlayIT tunnel", "conflict": True}

    server_name, server_port = row["name"], row["serverport"]
    is_bedrock = row["type"] in BEDROCK_TYPES
    subdomain = _slugify(server_name)

    log.info("Creating PlayIT tunnel: name=%s, local_port=%d, region=%s, protocol=%s",
             subdomain, server_port, region or "default", "bedrock" if is_bedrock else "java")
    tunnel_address = asyncio.run(create_tunnel(
        tunnel_name=subdomain, tunnel_port=server_port, region=region, subscription=subscription, agent=agent,
        protocol="bedrock" if is_bedrock else "java",
    ))
    if not tunnel_address:
        return {"success": False, "message": "PlayIT tunnel creation failed"}

    if is_bedrock:
        tunnel_address, external_port = _split_bedrock_address(tunnel_address)
    else:
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

    # A tunnel now exists, so this server is no longer local-only.
    try:
        with get_db() as conn:
            conn.execute("UPDATE servers SET local_only = 0 WHERE id = ?", (db_server_id,))
    except sqlite3.Error as exc:
        log.warning("Failed to clear local_only flag for db_id=%d: %s", db_server_id, exc)

    connect_address, dns_warning = _create_optional_dns(
        db_server_id, subdomain, tunnel_address, external_port, is_bedrock,
    )
    log.info(
        "Tunnel created for server db_id=%d: connect_address=%s, external_port=%s",
        db_server_id, connect_address, external_port,
    )
    return {
        "success": True,
        "message": "PlayIT tunnel created successfully",
        "tunnel_address": tunnel_address,
        "external_port": external_port,
        "connect_address": connect_address,
        **({"warning": dns_warning} if dns_warning else {}),
    }


def rename_server_subdomain(db_server_id: int, new_subdomain: str) -> dict:
    """Change the optional Cloudflare name without replacing the PlayIT tunnel."""
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", new_subdomain):
        return {"success": False, "message": "Invalid subdomain label", "invalid": True}
    if not cloudflare_enabled():
        return {"success": False, "message": "Cloudflare is not configured", "invalid": True}
    with get_db() as conn:
        server = conn.execute("SELECT type FROM servers WHERE id = ?", (db_server_id,)).fetchone()
        if not server:
            return {"success": False, "message": f"No server found with ID {db_server_id}"}
        tunnel = conn.execute(
            "SELECT tunnel_address, external_port FROM playit_tunnels WHERE server_id = ?",
            (db_server_id,),
        ).fetchone()
        old_dns = conn.execute(
            "SELECT id, record_type, name, cloudflare_record_id FROM dns_records WHERE server_id = ?",
            (db_server_id,),
        ).fetchall()
    if not tunnel:
        return {"success": False, "message": "No PlayIT tunnel exists for this server", "invalid": True}
    if any(row["record_type"] == "CNAME" and row["name"].split(".")[0] == new_subdomain
           for row in old_dns):
        return {"success": True, "message": "Cloudflare subdomain is already set"}

    address, warning = _create_optional_dns(
        db_server_id, new_subdomain, tunnel["tunnel_address"],
        tunnel["external_port"], server["type"] in BEDROCK_TYPES,
    )
    if warning:
        return {"success": False, "message": warning}
    cleanup_failed = False
    for row in old_dns:
        if row["cloudflare_record_id"] and not delete_dns_record_by_id(row["cloudflare_record_id"]):
            cleanup_failed = True
            continue
        with get_db() as conn:
            conn.execute("DELETE FROM dns_records WHERE id = ?", (row["id"],))
    return {
        "success": True,
        "connect_address": address,
        "message": "Cloudflare subdomain updated",
        **({"warning": "Some old DNS records need manual removal"} if cleanup_failed else {}),
    }
