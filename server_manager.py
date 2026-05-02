"""
Core server provisioning and deprovisioning logic.

This module is the single source of truth for all server lifecycle operations.
It is consumed by both the Flask API (app.py) and the CLI scripts
(main.py, delete_server.py).

Provisioning sequence:
    1. Authenticate with Crafty Controller and create the game server.
    2. Persist the server record in the Neon PostgreSQL database.
    3. Create a PlayIT tunnel for the server's local port.
    4. Resolve the tunnel's external port via DNS SRV lookup.
    5. Create a Cloudflare CNAME record pointing the subdomain to the tunnel.
    6. Create a Cloudflare SRV record so Minecraft clients discover the port.

Deprovisioning sequence:
    1. Retrieve the server record and linked resources from the database.
    2. Delete the Crafty server.
    3. Delete all Cloudflare DNS records by their stored record IDs.
    4. Delete the database row, which cascades to playit_tunnels and dns_records.
"""

import asyncio
import os
import time
import requests
import urllib3
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

from playit_manager import create_tunnel, delete_tunnel
from cloudflare_manager import (
    create_dns_record,
    create_srv_record,
    lookup_minecraft_srv_port,
    delete_dns_record_by_id,
)
from logger import get_logger

load_dotenv()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = get_logger("server_manager")

# ---------------------------------------------------------------------------
# Supported server types
# Each key is the public API identifier; the nested dict maps to Crafty's
# download_jar_create_data fields.
# ---------------------------------------------------------------------------
SERVER_TYPES = {
    "paper":   {"category": "mc_java_servers", "type": "paper"},
    "forge":   {"category": "mc_java_servers", "type": "forge-installer"},
    "fabric":  {"category": "mc_java_servers", "type": "fabric"},
    "vanilla": {"category": "mc_java_servers", "type": "vanilla"},
    "purpur":  {"category": "mc_java_servers", "type": "purpur"},
}

_base_url    = os.getenv("BASE_URL", "https://localhost:8443")
_crafty_user = os.getenv("CRAFTY_USER", "admin")
_crafty_pass = os.getenv("CRAFTY_PASS", "admin")


def _get_db() -> psycopg2.extensions.connection:
    """Open and return a new database connection."""
    return psycopg2.connect(
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        sslmode="require",
    )


def crafty_login() -> str | None:
    """Authenticate with Crafty Controller and return a bearer token.

    Returns:
        A JWT token string on success, or ``None`` on failure.
    """
    try:
        r = requests.post(
            f"{_base_url}/api/v2/auth/login",
            json={"username": _crafty_user, "password": _crafty_pass},
            verify=False,
        )
        data = r.json()
        if r.status_code == 200 and data.get("status") == "ok":
            log.debug("Crafty authentication successful")
            return data["data"]["token"]
        error_detail = data.get("error_data") or data.get("error") or r.text
        log.error("Crafty authentication failed: HTTP %d — %s", r.status_code, error_detail)
        return None
    except requests.exceptions.ConnectionError:
        log.error("Cannot reach Crafty Controller at %s", _base_url)
        return None


def provision_server(
    server_name: str,
    server_type: str = "paper",
    version: str = "1.21.4",
    server_port: int = 25565,
    mem_min: int = 2,
    mem_max: int = 4,
    subscription: str | None = None,
) -> dict:
    """Provision a complete Minecraft server stack.

    Creates a Crafty game server, a PlayIT tunnel, and the required Cloudflare
    DNS records in sequence.  Each step's result is persisted to the database.

    Args:
        server_name: Display name for the server.
        server_type: One of the keys in SERVER_TYPES (e.g. "paper", "forge").
        version:     Minecraft version string (e.g. "1.21.4").
        server_port: Local TCP port for the game server.
        mem_min:     Minimum JVM heap size in GB.
        mem_max:     Maximum JVM heap size in GB.
        subscription: Network subscription level: "premium" or "free".
                    Defaults to PLAYIT_SUBSCRIPTION env var or "premium".

    Returns:
        A dict containing ``success`` (bool) and ``message`` (str).
        On success, also includes ``server_id``, ``crafty_id``,
        ``connect_address``, ``tunnel_address``, and ``external_port``.
    """
    if server_type not in SERVER_TYPES:
        return {
            "success": False,
            "message": f"Unknown server type '{server_type}'. Valid types: {list(SERVER_TYPES)}",
        }

    subdomain = server_name.lower().replace(" ", "-")
    type_cfg  = SERVER_TYPES[server_type]
    log.info(
        "Provisioning server: name=%s, type=%s, version=%s, port=%d",
        server_name, server_type, version, server_port,
    )

    # Step 1: Authenticate with Crafty
    token = crafty_login()
    if not token:
        return {"success": False, "message": "Could not authenticate with Crafty Controller"}

    headers = {"Authorization": f"Bearer {token}"}
    crafty_payload = {
        "name": server_name,
        "monitoring_type": "minecraft_java",
        "minecraft_java_monitoring_data": {"host": "127.0.0.1", "port": server_port},
        "create_type": "minecraft_java",
        "minecraft_java_create_data": {
            "create_type": "download_jar",
            "download_jar_create_data": {
                "category": type_cfg["category"],
                "type": type_cfg["type"],
                "version": version,
                "mem_min": mem_min,
                "mem_max": mem_max,
                "server_properties_port": server_port,
                "agree_to_eula": True,
            },
        },
    }

    # Step 2: Create Crafty server
    try:
        r = requests.post(
            f"{_base_url}/api/v2/servers",
            json=crafty_payload,
            headers=headers,
            verify=False,
        )
        data = r.json()
    except requests.exceptions.RequestException as exc:
        log.error("Crafty server creation request failed: %s", exc)
        return {"success": False, "message": f"Crafty server creation failed: {exc}"}
    except ValueError as exc:
        log.error("Crafty returned non-JSON response (HTTP %d): %s", r.status_code, r.text[:200])
        return {"success": False, "message": "Crafty returned an unexpected response"}

    # Crafty sometimes returns a non-2xx status but still creates the server and
    # includes new_server_id in the body (known Crafty behaviour during jar download).
    crafty_server_id = (data.get("data") or {}).get("new_server_id")
    if crafty_server_id:
        log.info("Crafty server created: crafty_id=%s (HTTP %d)", crafty_server_id, r.status_code)
    else:
        error_detail = data.get("error_data") or data.get("error") or r.text
        log.error("Crafty server creation failed (HTTP %d): %s", r.status_code, error_detail)
        return {"success": False, "message": f"Crafty server creation failed: {error_detail}"}

    # Step 2b: Start the server
    log.info("Waiting for Crafty to finish jar download before starting...")
    time.sleep(15)
    try:
        r2 = requests.post(
            f"{_base_url}/api/v2/servers/{crafty_server_id}/action/start_server",
            headers=headers,
            verify=False,
        )
        if r2.ok:
            log.info("Crafty server start triggered: crafty_id=%s", crafty_server_id)
        else:
            log.warning("Crafty start returned HTTP %d: %s", r2.status_code, r2.text)
    except requests.exceptions.RequestException as exc:
        log.warning("Could not start Crafty server: %s", exc)

    # Step 3: Persist server record
    db_server_id = None
    try:
        conn = _get_db()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO servers (name, type, version, serverport, craftyid, createdat)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (server_name, server_type, version, server_port, crafty_server_id, datetime.now()),
        )
        conn.commit()
        cur.execute("SELECT id FROM servers WHERE craftyid = %s", (crafty_server_id,))
        db_server_id = cur.fetchone()[0]
        log.info("Server record persisted: db_id=%d", db_server_id)
    except psycopg2.Error as exc:
        log.error("Database error while persisting server record: %s", exc)
        return {"success": False, "message": f"Database error: {exc}"}
    finally:
        conn.close()

    # Step 4: Create PlayIT tunnel
    log.info("Creating PlayIT tunnel: name=%s, local_port=%d", subdomain, server_port)
    tunnel_address = asyncio.run(create_tunnel(tunnel_name=subdomain, tunnel_port=server_port, subscription=subscription))
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
        conn = _get_db()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO playit_tunnels"
            " (server_id, tunnel_name, tunnel_address, local_port, external_port)"
            " VALUES (%s, %s, %s, %s, %s)",
            (db_server_id, subdomain, tunnel_address, server_port, external_port),
        )
        conn.commit()
        log.debug("Tunnel record persisted: address=%s", tunnel_address)
    except psycopg2.Error as exc:
        log.warning("Failed to persist tunnel record: %s", exc)
    finally:
        conn.close()

    # Step 5: Create Cloudflare CNAME record
    log.info("Creating Cloudflare CNAME: %s -> %s", subdomain, tunnel_address)
    cname_result = create_dns_record(subdomain=subdomain, target=tunnel_address)
    if not cname_result:
        log.error("Cloudflare CNAME creation failed for subdomain=%s", subdomain)
        return {"success": False, "message": "Cloudflare CNAME creation failed", "tunnel_address": tunnel_address}

    dns_name, cname_cf_id = cname_result

    try:
        conn = _get_db()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO dns_records"
            " (server_id, record_type, name, target, cloudflare_record_id)"
            " VALUES (%s, %s, %s, %s, %s)",
            (db_server_id, "CNAME", dns_name, tunnel_address, cname_cf_id),
        )
        conn.commit()
        log.debug("CNAME record persisted: name=%s, cf_id=%s", dns_name, cname_cf_id)
    except psycopg2.Error as exc:
        log.warning("Failed to persist CNAME record: %s", exc)
    finally:
        conn.close()

    # Step 6: Create Cloudflare SRV record
    if external_port:
        log.info("Creating Cloudflare SRV record: port=%d", external_port)
        srv_cf_id = create_srv_record(subdomain=subdomain, target=tunnel_address, port=external_port)
        if srv_cf_id:
            srv_name = f"_minecraft._tcp.{dns_name}"
            try:
                conn = _get_db()
                cur  = conn.cursor()
                cur.execute(
                    "INSERT INTO dns_records"
                    " (server_id, record_type, name, target, port, cloudflare_record_id)"
                    " VALUES (%s, %s, %s, %s, %s, %s)",
                    (db_server_id, "SRV", srv_name, tunnel_address, external_port, srv_cf_id),
                )
                conn.commit()
                log.debug("SRV record persisted: name=%s, cf_id=%s", srv_name, srv_cf_id)
            except psycopg2.Error as exc:
                log.warning("Failed to persist SRV record: %s", exc)
            finally:
                conn.close()

    log.info(
        "Server provisioned successfully: db_id=%d, connect_address=%s",
        db_server_id, dns_name,
    )
    return {
        "success": True,
        "message": "Server provisioned successfully",
        "server_id": db_server_id,
        "crafty_id": crafty_server_id,
        "connect_address": dns_name,
        "tunnel_address": tunnel_address,
        "external_port": external_port,
    }


def deprovision_server(db_server_id: int) -> dict:
    """Remove a server and all associated resources.

    Deletes the Crafty game server, all Cloudflare DNS records, and the
    database row (which cascades to playit_tunnels and dns_records).

    Args:
        db_server_id: The primary key of the server in the ``servers`` table.

    Returns:
        A dict containing ``success`` (bool) and ``message`` (str).
    """
    log.info("Deprovisioning server: db_id=%d", db_server_id)

    try:
        conn = _get_db()
        cur  = conn.cursor()
        cur.execute("SELECT id, name, craftyid FROM servers WHERE id = %s", (db_server_id,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "message": f"No server found with ID {db_server_id}"}

        _, server_name, crafty_server_id = row

        cur.execute(
            "SELECT cloudflare_record_id, name FROM dns_records WHERE server_id = %s",
            (db_server_id,),
        )
        dns_rows = cur.fetchall()

        cur.execute(
            "SELECT tunnel_name FROM playit_tunnels WHERE server_id = %s",
            (db_server_id,),
        )
        tunnel_rows = cur.fetchall()
    except psycopg2.Error as exc:
        log.error("Database error while fetching server record: %s", exc)
        return {"success": False, "message": f"Database error: {exc}"}
    finally:
        conn.close()

    # Delete Crafty server
    if crafty_server_id:
        token = crafty_login()
        if token:
            try:
                r = requests.delete(
                    f"{_base_url}/api/v2/servers/{crafty_server_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    verify=False,
                )
                if r.ok:
                    log.info("Crafty server deleted: crafty_id=%s", crafty_server_id)
                else:
                    log.warning("Crafty deletion returned HTTP %d: %s", r.status_code, r.text)
            except requests.exceptions.RequestException as exc:
                log.warning("Error deleting Crafty server: %s", exc)
        else:
            log.warning("Skipping Crafty deletion — authentication failed")
    else:
        log.debug("No Crafty ID stored for db_id=%d, skipping Crafty deletion", db_server_id)

    # Delete PlayIT tunnels
    for (tunnel_name,) in tunnel_rows:
        log.info("Deleting PlayIT tunnel: name=%s", tunnel_name)
        success = asyncio.run(delete_tunnel(tunnel_name))
        if not success:
            log.warning("Could not delete PlayIT tunnel '%s' — may need manual removal", tunnel_name)

    # Delete Cloudflare DNS records
    for cf_id, name in dns_rows:
        log.info("Deleting Cloudflare record: name=%s, cf_id=%s", name, cf_id)
        delete_dns_record_by_id(cf_id)

    # Delete database row (cascades to playit_tunnels and dns_records)
    try:
        conn = _get_db()
        cur  = conn.cursor()
        cur.execute("DELETE FROM servers WHERE id = %s", (db_server_id,))
        conn.commit()
        log.info(
            "Server deprovisioned: db_id=%d, name=%s (tunnel + DNS records cascaded)",
            db_server_id, server_name,
        )
    except psycopg2.Error as exc:
        log.error("Database error during server deletion: %s", exc)
        return {"success": False, "message": f"Database error during deletion: {exc}"}
    finally:
        conn.close()

    return {"success": True, "message": f"Server '{server_name}' deleted successfully"}


def list_servers() -> list[dict]:
    """Return all servers with their associated tunnels and DNS records.

    Returns:
        A list of server dicts.  Each dict includes ``id``, ``name``,
        ``type``, ``version``, ``port``, ``crafty_id``, ``created_at``,
        ``tunnels``, and ``dns_records``.
    """
    try:
        conn = _get_db()
        cur  = conn.cursor()
        cur.execute(
            "SELECT id, name, type, version, serverport, craftyid, createdat"
            " FROM servers ORDER BY id"
        )
        servers = cur.fetchall()
        result = []
        for sid, name, stype, version, port, crafty_id, created_at in servers:
            cur.execute(
                "SELECT tunnel_address, local_port, external_port"
                " FROM playit_tunnels WHERE server_id = %s",
                (sid,),
            )
            tunnels = [
                {"address": r[0], "local_port": r[1], "external_port": r[2]}
                for r in cur.fetchall()
            ]
            cur.execute(
                "SELECT record_type, name, target, port"
                " FROM dns_records WHERE server_id = %s",
                (sid,),
            )
            dns = [
                {"type": r[0], "name": r[1], "target": r[2], "port": r[3]}
                for r in cur.fetchall()
            ]
            result.append({
                "id": sid,
                "name": name,
                "type": stype,
                "version": version,
                "port": port,
                "crafty_id": crafty_id,
                "created_at": created_at.isoformat() if created_at else None,
                "tunnels": tunnels,
                "dns_records": dns,
            })
        log.debug("Listed %d servers", len(result))
        return result
    except psycopg2.Error as exc:
        log.error("Database error while listing servers: %s", exc)
        return []
    finally:
        conn.close()


def create_server_tunnel(db_server_id: int, region: str | None = None, subscription: str | None = None) -> dict:
    """Create a PlayIT tunnel and Cloudflare DNS records for an existing server.

    Args:
        db_server_id: Database ID of the server.
        region: Optional server region (e.g., "Germany", "Seattle", "Japan").
                Defaults to PLAYIT_REGION env var.
        subscription: Optional network subscription level: "premium" or "free".
                    Defaults to PLAYIT_SUBSCRIPTION env var or "premium".
    """
    try:
        conn = _get_db()
        cur  = conn.cursor()
        cur.execute("SELECT name, serverport FROM servers WHERE id = %s", (db_server_id,))
        row = cur.fetchone()
    except psycopg2.Error as exc:
        log.error("Database error fetching server %d: %s", db_server_id, exc)
        return {"success": False, "message": f"Database error: {exc}"}
    finally:
        conn.close()

    if not row:
        return {"success": False, "message": f"No server found with ID {db_server_id}"}

    server_name, server_port = row
    subdomain = server_name.lower().replace(" ", "-")

    log.info("Creating PlayIT tunnel: name=%s, local_port=%d, region=%s", subdomain, server_port, region or "default")
    tunnel_address = asyncio.run(create_tunnel(tunnel_name=subdomain, tunnel_port=server_port, region=region, subscription=subscription))
    if not tunnel_address:
        return {"success": False, "message": "PlayIT tunnel creation failed"}

    external_port = lookup_minecraft_srv_port(tunnel_address)
    if external_port:
        log.debug("External port resolved: %d", external_port)
    else:
        log.warning("Could not resolve external port for tunnel %s", tunnel_address)

    try:
        conn = _get_db()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO playit_tunnels"
            " (server_id, tunnel_name, tunnel_address, local_port, external_port)"
            " VALUES (%s, %s, %s, %s, %s)",
            (db_server_id, subdomain, tunnel_address, server_port, external_port),
        )
        conn.commit()
    except psycopg2.Error as exc:
        log.warning("Failed to persist tunnel record: %s", exc)
    finally:
        conn.close()

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
        conn = _get_db()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO dns_records"
            " (server_id, record_type, name, target, cloudflare_record_id)"
            " VALUES (%s, %s, %s, %s, %s)",
            (db_server_id, "CNAME", dns_name, tunnel_address, cname_cf_id),
        )
        conn.commit()
    except psycopg2.Error as exc:
        log.warning("Failed to persist CNAME record: %s", exc)
    finally:
        conn.close()

    if external_port:
        srv_cf_id = create_srv_record(subdomain=subdomain, target=tunnel_address, port=external_port)
        if srv_cf_id:
            srv_name = f"_minecraft._tcp.{dns_name}"
            try:
                conn = _get_db()
                cur  = conn.cursor()
                cur.execute(
                    "INSERT INTO dns_records"
                    " (server_id, record_type, name, target, port, cloudflare_record_id)"
                    " VALUES (%s, %s, %s, %s, %s, %s)",
                    (db_server_id, "SRV", srv_name, tunnel_address, external_port, srv_cf_id),
                )
                conn.commit()
            except psycopg2.Error as exc:
                log.warning("Failed to persist SRV record: %s", exc)
            finally:
                conn.close()

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
        conn = _get_db()
        cur  = conn.cursor()
        cur.execute("SELECT id FROM servers WHERE id = %s", (db_server_id,))
        if not cur.fetchone():
            return {"success": False, "message": f"No server found with ID {db_server_id}"}
        cur.execute(
            "SELECT cloudflare_record_id, record_type, name"
            " FROM dns_records WHERE server_id = %s",
            (db_server_id,),
        )
        old_dns_rows = cur.fetchall()
        cur.execute(
            "SELECT tunnel_address, external_port FROM playit_tunnels WHERE server_id = %s",
            (db_server_id,),
        )
        tunnel_row = cur.fetchone()
    except psycopg2.Error as exc:
        log.error("Database error fetching server %d: %s", db_server_id, exc)
        return {"success": False, "message": f"Database error: {exc}"}
    finally:
        conn.close()

    if not tunnel_row:
        return {"success": False, "message": "No tunnel found for this server — create one first"}

    tunnel_address, external_port = tunnel_row

    for cf_id, rtype, name in old_dns_rows:
        log.info("Deleting old DNS record: type=%s name=%s cf_id=%s", rtype, name, cf_id)
        delete_dns_record_by_id(cf_id)

    try:
        conn = _get_db()
        cur  = conn.cursor()
        cur.execute("DELETE FROM dns_records WHERE server_id = %s", (db_server_id,))
        conn.commit()
    except psycopg2.Error as exc:
        log.warning("Failed to delete old DNS records from DB: %s", exc)
    finally:
        conn.close()

    log.info("Creating Cloudflare CNAME: %s -> %s", new_subdomain, tunnel_address)
    cname_result = create_dns_record(subdomain=new_subdomain, target=tunnel_address)
    if not cname_result:
        return {"success": False, "message": "Cloudflare CNAME creation failed"}

    dns_name, cname_cf_id = cname_result

    try:
        conn = _get_db()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO dns_records"
            " (server_id, record_type, name, target, cloudflare_record_id)"
            " VALUES (%s, %s, %s, %s, %s)",
            (db_server_id, "CNAME", dns_name, tunnel_address, cname_cf_id),
        )
        conn.commit()
    except psycopg2.Error as exc:
        log.warning("Failed to persist new CNAME record: %s", exc)
    finally:
        conn.close()

    if external_port:
        srv_cf_id = create_srv_record(subdomain=new_subdomain, target=tunnel_address, port=external_port)
        if srv_cf_id:
            srv_name = f"_minecraft._tcp.{dns_name}"
            try:
                conn = _get_db()
                cur  = conn.cursor()
                cur.execute(
                    "INSERT INTO dns_records"
                    " (server_id, record_type, name, target, port, cloudflare_record_id)"
                    " VALUES (%s, %s, %s, %s, %s, %s)",
                    (db_server_id, "SRV", srv_name, tunnel_address, external_port, srv_cf_id),
                )
                conn.commit()
            except psycopg2.Error as exc:
                log.warning("Failed to persist new SRV record: %s", exc)
            finally:
                conn.close()

    try:
        conn = _get_db()
        cur  = conn.cursor()
        cur.execute(
            "UPDATE playit_tunnels SET tunnel_name = %s WHERE server_id = %s",
            (new_subdomain, db_server_id),
        )
        conn.commit()
    except psycopg2.Error as exc:
        log.warning("Failed to update tunnel_name: %s", exc)
    finally:
        conn.close()

    log.info(
        "Subdomain renamed for server db_id=%d: new connect_address=%s",
        db_server_id, dns_name,
    )
    return {
        "success": True,
        "message": "Subdomain renamed successfully",
        "connect_address": dns_name,
    }
