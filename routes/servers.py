"""Server CRUD, lifecycle, console command, stats, logs, and networking routes."""

import sqlite3
import threading

from flask import Blueprint, jsonify, request

import docker_manager
import progress_store
import properties_manager
from auth_helpers import authorize
from db import get_db
from docker_manager import SERVER_TYPES
from logger import get_logger
from server_manager import (
    _create_server_record,
    _provision_resources,
    create_server_tunnel,
    deprovision_server,
    list_servers,
    provision_server,
    rename_server_subdomain,
)

log = get_logger("api")

servers_bp = Blueprint("servers", __name__, url_prefix="/api")


def _server_exists(server_id: int) -> bool:
    with get_db() as conn:
        return conn.execute("SELECT 1 FROM servers WHERE id = ?", (server_id,)).fetchone() is not None


def _serialize_server(row, *, include_runtime: bool = True) -> dict:
    server = dict(row)
    server["port"] = server.pop("serverport")
    server["mem_min"] = server.pop("mem_min_gb")
    server["mem_max"] = server.pop("mem_max_gb")
    server["created_at"] = server.pop("createdat")
    server.pop("rcon_password", None)
    if include_runtime:
        server["runtime_status"] = docker_manager.runtime_status(server["id"])
    return server


# ---------------------------------------------------------------------------
# GET /api/server-types
# ---------------------------------------------------------------------------
@servers_bp.route("/server-types", methods=["GET"])
def get_server_types():
    auth_err = authorize()
    if auth_err:
        return auth_err
    return jsonify({"server_types": list(SERVER_TYPES.keys())})


# ---------------------------------------------------------------------------
# GET /api/servers
# ---------------------------------------------------------------------------
@servers_bp.route("/servers", methods=["GET"])
def get_servers():
    auth_err = authorize()
    if auth_err:
        return auth_err
    servers = list_servers()
    log.info("Listed %d servers", len(servers))
    return jsonify({"servers": servers})


# ---------------------------------------------------------------------------
# GET /api/servers/<id>
# ---------------------------------------------------------------------------
@servers_bp.route("/servers/<int:server_id>", methods=["GET"])
def get_server_detail(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err
    with get_db() as conn:
        row = conn.execute("SELECT * FROM servers WHERE id = ?", (server_id,)).fetchone()
    if not row:
        return jsonify({"success": False, "message": "Server not found"}), 404

    server = _serialize_server(row)
    return jsonify({"success": True, "server": server})


# ---------------------------------------------------------------------------
# POST /api/servers
#
# Request body (JSON):
#   name      string  required  Server display name.
#   type      string  optional  paper|forge|fabric|vanilla|purpur|bedrock
#                               Default: paper
#   version   string  optional  Minecraft version (e.g. "1.21.4"), or "LATEST".
#                               Default: 1.21.4 (Java) / LATEST (Bedrock)
#   port      int     optional  Host server port (1024-65535).
#                               Default: 25565 (Java, TCP) / 19132 (Bedrock, UDP)
#   mem_min   int     optional  Minimum JVM heap in GB. Ignored for Bedrock (no JVM).
#                               Default: 2
#   mem_max   int     optional  Maximum JVM heap in GB (Java) or container memory
#                               cap in GB (Bedrock). Default: 4
#   subscription string optional Network subscription level: "premium" or "free".
#                               Default: premium (from PLAYIT_SUBSCRIPTION env var)
#   agent     string  optional  Agent name for the tunnel (e.g., "US-East", "EU-Central").
#                               Default: first available (from PLAYIT_AGENT env var)
#
# Bedrock servers have no SRV-based port discovery, no RCON, and are not
# affected by loader_version. See README.md for full Bedrock caveats.
# ---------------------------------------------------------------------------
@servers_bp.route("/servers", methods=["POST"])
def create_server():
    auth_err = authorize()
    if auth_err:
        return auth_err

    body = request.get_json(silent=True) or {}

    name = body.get("name", "").strip()
    if not name:
        return jsonify({"error": "'name' is required"}), 400

    server_type = body.get("type", "paper").lower()
    if server_type not in SERVER_TYPES:
        return jsonify({
            "error": f"Invalid server type '{server_type}'",
            "valid_types": list(SERVER_TYPES.keys()),
        }), 400
    is_bedrock = server_type == "bedrock"

    version = body.get("version") or ("LATEST" if is_bedrock else "1.21.4")
    port    = body.get("port")   or (19132 if is_bedrock else 25565)
    mem_min = body.get("mem_min", 2)
    mem_max = body.get("mem_max", 4)
    loader_version   = body.get("loader_version")  # None = image default
    subscription = body.get("subscription")
    agent = body.get("agent")
    initial_properties = body.get("properties")

    if not isinstance(port, int) or not (1024 <= port <= 65535):
        return jsonify({"error": "'port' must be an integer between 1024 and 65535"}), 400
    if not isinstance(mem_min, int) or not isinstance(mem_max, int) or mem_min < 1 or mem_max < 1:
        return jsonify({"error": "'mem_min' and 'mem_max' must be positive integers"}), 400
    if not is_bedrock and mem_max < mem_min:
        # mem_min is ignored for bedrock (no JVM heap), so it has no ordering
        # relationship with mem_max (the container memory cap) there.
        return jsonify({"error": "'mem_max' must be >= 'mem_min'"}), 400
    if subscription and subscription.lower() not in ("premium", "free"):
        return jsonify({"error": "'subscription' must be 'premium' or 'free'"}), 400
    if initial_properties is not None and not isinstance(initial_properties, dict):
        return jsonify({"error": "'properties' must be an object when provided"}), 400

    log.info(
        "Server creation requested: name=%s, type=%s, version=%s, port=%d",
        name, server_type, version, port,
    )

    # Step 1 (synchronous): create DB record → get server_id immediately
    record = _create_server_record(name, server_type, version, loader_version,
                                    port, mem_min, mem_max)
    if not record["success"]:
        log.error("Server creation record failed: %s", record.get("message"))
        return jsonify(record), 409 if record.get("conflict") else 400

    server_id = record["server_id"]
    subdomain  = record["subdomain"]
    progress_store.update(server_id, action="provision", percent=5,
                          step="Database record created")

    # Steps 2-6 (async): container, PlayIT, Cloudflare
    def _bg_provision():
        result = _provision_resources(server_id, subdomain, port, subscription, agent)
        if result.get("success") and initial_properties:
            properties_manager.apply_initial_properties(server_id, initial_properties)

    threading.Thread(target=_bg_provision, daemon=True).start()
    log.info("Server provisioning started (background): db_id=%d", server_id)
    return jsonify({
        "success": True,
        "message": "Server provisioning started",
        "server_id": server_id,
    }), 202


# ---------------------------------------------------------------------------
# DELETE /api/servers/<id>
# ---------------------------------------------------------------------------
@servers_bp.route("/servers/<int:server_id>", methods=["DELETE"])
def delete_server(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err
    if not _server_exists(server_id):
        return jsonify({"success": False, "message": "Server not found"}), 404

    # Guard against concurrent deletion
    prog = progress_store.get(server_id)
    if prog["action"] == "delete" and prog["status"] == "in_progress":
        return jsonify({"success": False, "message": "Deletion already in progress"}), 409

    progress_store.update(server_id, action="delete", percent=2, step="Deletion queued")

    def _bg_delete():
        deprovision_server(server_id)

    threading.Thread(target=_bg_delete, daemon=True).start()
    log.info("Server deletion started (background): db_id=%d", server_id)
    return jsonify({
        "success": True,
        "message": "Server deletion started",
        "server_id": server_id,
    }), 202


# ---------------------------------------------------------------------------
# GET /api/servers/<id>/progress
# ---------------------------------------------------------------------------
@servers_bp.route("/servers/<int:server_id>/progress", methods=["GET"])
def server_progress(server_id: int):
    """Return real-time provisioning or deletion progress for a server.

    Poll this endpoint while waiting for a 202 response from
    POST /api/servers or DELETE /api/servers/<id> to complete.
    """
    auth_err = authorize()
    if auth_err:
        return auth_err
    return jsonify(progress_store.get(server_id)), 200


# ---------------------------------------------------------------------------
# POST /api/servers/<id>/start|stop|restart|kill
# ---------------------------------------------------------------------------
@servers_bp.route("/servers/<int:server_id>/start", methods=["POST"])
def start_server(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err
    if not _server_exists(server_id):
        return jsonify({"success": False, "message": "Server not found"}), 404
    success, message = docker_manager.start_server(server_id)
    return jsonify({"success": success, "message": message}), 200 if success else 500


@servers_bp.route("/servers/<int:server_id>/stop", methods=["POST"])
def stop_server(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err
    if not _server_exists(server_id):
        return jsonify({"success": False, "message": "Server not found"}), 404
    success, message = docker_manager.stop_server(server_id)
    return jsonify({"success": success, "message": message}), 200 if success else 500


@servers_bp.route("/servers/<int:server_id>/restart", methods=["POST"])
def restart_server(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err
    if not _server_exists(server_id):
        return jsonify({"success": False, "message": "Server not found"}), 404
    success, message = docker_manager.restart_server(server_id)
    return jsonify({"success": success, "message": message}), 200 if success else 500


@servers_bp.route("/servers/<int:server_id>/kill", methods=["POST"])
def kill_server(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err
    if not _server_exists(server_id):
        return jsonify({"success": False, "message": "Server not found"}), 404
    success, message = docker_manager.kill_server(server_id)
    return jsonify({"success": success, "message": message}), 200 if success else 500


# ---------------------------------------------------------------------------
# POST /api/servers/<id>/command
# Body: { "command": "say Hello" }
# ---------------------------------------------------------------------------
@servers_bp.route("/servers/<int:server_id>/command", methods=["POST"])
def send_command(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err
    if not _server_exists(server_id):
        return jsonify({"success": False, "message": "Server not found"}), 404

    body = request.get_json(silent=True) or {}
    command = body.get("command", "").strip()
    if not command:
        return jsonify({"success": False, "message": "'command' is required"}), 400

    try:
        output = docker_manager.send_rcon(server_id, command)
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 500
    return jsonify({"success": True, "message": "Command sent", "output": output}), 200


# ---------------------------------------------------------------------------
# GET /api/servers/<id>/stats
# ---------------------------------------------------------------------------
@servers_bp.route("/servers/<int:server_id>/stats", methods=["GET"])
def server_stats(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err
    if not _server_exists(server_id):
        return jsonify({"success": False, "message": "Server not found"}), 404
    stats = docker_manager.get_stats(server_id)
    return jsonify({"success": True, "data": stats}), 200


# ---------------------------------------------------------------------------
# GET /api/servers/<id>/logs?tail=200
# ---------------------------------------------------------------------------
@servers_bp.route("/servers/<int:server_id>/logs", methods=["GET"])
def server_logs(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err
    if not _server_exists(server_id):
        return jsonify({"success": False, "message": "Server not found"}), 404
    tail = request.args.get("tail", default=200, type=int)
    lines = docker_manager.get_logs(server_id, tail=tail)
    return jsonify({"success": True, "data": lines}), 200


# ---------------------------------------------------------------------------
# POST /api/servers/<id>/tunnel
# Body (JSON, optional): { "region": ..., "subscription": ..., "agent": ... }
# ---------------------------------------------------------------------------
@servers_bp.route("/servers/<int:server_id>/tunnel", methods=["POST"])
def create_tunnel_endpoint(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err

    body = request.get_json(silent=True) or {}
    region = body.get("region")
    subscription = body.get("subscription")
    agent = body.get("agent")

    if subscription and subscription.lower() not in ("premium", "free"):
        return jsonify({"error": "'subscription' must be 'premium' or 'free'"}), 400

    log.info("Tunnel creation requested: db_id=%d, region=%s, subscription=%s, agent=%s", server_id, region or "default", subscription or "default", agent or "default")
    result = create_server_tunnel(server_id, region=region, subscription=subscription, agent=agent)

    if result["success"]:
        log.info("Tunnel created: db_id=%d, address=%s", server_id, result.get("connect_address"))
        return jsonify(result), 201
    if "No server found" in result.get("message", ""):
        return jsonify(result), 404
    log.error("Tunnel creation failed: %s", result.get("message"))
    return jsonify(result), 500


# ---------------------------------------------------------------------------
# PATCH /api/servers/<id>/subdomain
# Body: { "subdomain": "new-name" }
# ---------------------------------------------------------------------------
@servers_bp.route("/servers/<int:server_id>/subdomain", methods=["PATCH"])
def rename_subdomain(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err

    body = request.get_json(silent=True) or {}
    new_subdomain = body.get("subdomain", "").strip().lower()
    if not new_subdomain:
        return jsonify({"success": False, "message": "'subdomain' is required"}), 400

    log.info("Subdomain rename requested: db_id=%d, new_subdomain=%s", server_id, new_subdomain)
    result = rename_server_subdomain(server_id, new_subdomain)

    if result["success"]:
        return jsonify(result), 200
    if "No server found" in result.get("message", ""):
        return jsonify(result), 404
    log.error("Subdomain rename failed: %s", result.get("message"))
    return jsonify(result), 500


# ---------------------------------------------------------------------------
# PATCH /api/servers/<id>/name
# Body: { "name": "New Server Name" }
# ---------------------------------------------------------------------------
@servers_bp.route("/servers/<int:server_id>/name", methods=["PATCH"])
def rename_server(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err

    body = request.get_json(silent=True) or {}
    new_name = body.get("name", "").strip()
    if not new_name:
        return jsonify({"success": False, "message": "'name' is required"}), 400

    if not _server_exists(server_id):
        return jsonify({"success": False, "message": "Server not found"}), 404

    try:
        with get_db() as conn:
            conn.execute("UPDATE servers SET name = ? WHERE id = ?", (new_name, server_id))
    except sqlite3.Error as exc:
        return jsonify({"success": False, "message": f"Database error: {exc}"}), 500

    log.info("Server renamed: db_id=%d, new_name=%s", server_id, new_name)
    return jsonify({"success": True, "message": f"Server renamed to '{new_name}'"}), 200


# ---------------------------------------------------------------------------
# PATCH /api/servers/<id>/port
# Body: { "port": 25566 }
# ---------------------------------------------------------------------------
@servers_bp.route("/servers/<int:server_id>/port", methods=["PATCH"])
def update_server_port(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err

    body = request.get_json(silent=True) or {}
    new_port = body.get("port")
    if not isinstance(new_port, int) or not (1024 <= new_port <= 65535):
        return jsonify({"success": False, "message": "'port' must be an integer between 1024 and 65535"}), 400

    with get_db() as conn:
        row = conn.execute("SELECT * FROM servers WHERE id = ?", (server_id,)).fetchone()
    if not row:
        return jsonify({"success": False, "message": "Server not found"}), 404

    try:
        with get_db() as conn:
            conn.execute("UPDATE servers SET serverport = ? WHERE id = ?", (new_port, server_id))
            updated_row = conn.execute("SELECT * FROM servers WHERE id = ?", (server_id,)).fetchone()
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Port already in use by another server"}), 409

    try:
        docker_manager.recreate_server(updated_row)
    except Exception as exc:
        return jsonify({"success": False, "message": f"Port updated in DB but container recreate failed: {exc}"}), 500

    log.info("Server port updated: db_id=%d, new_port=%d", server_id, new_port)
    return jsonify({
        "success": True,
        "message": f"Port updated to {new_port}",
        "port": new_port,
        "warning": "The PlayIT tunnel and DNS records still point at the old port. "
                   "Recreate the tunnel via POST /api/servers/<id>/tunnel if needed.",
    }), 200


# ---------------------------------------------------------------------------
# PATCH /api/servers/<id>/ram
# Body: { "mem_min": 2, "mem_max": 4 }  (values in GB)
# ---------------------------------------------------------------------------
@servers_bp.route("/servers/<int:server_id>/ram", methods=["PATCH"])
def update_server_ram(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err

    body = request.get_json(silent=True) or {}
    mem_min = body.get("mem_min")
    mem_max = body.get("mem_max")
    if not isinstance(mem_min, int) or not isinstance(mem_max, int) or mem_min < 1 or mem_max < 1:
        return jsonify({"success": False, "message": "'mem_min' and 'mem_max' must be positive integers"}), 400

    with get_db() as conn:
        row = conn.execute("SELECT * FROM servers WHERE id = ?", (server_id,)).fetchone()
    if not row:
        return jsonify({"success": False, "message": "Server not found"}), 404

    # mem_min is ignored for bedrock (no JVM heap), so it has no ordering
    # relationship with mem_max (the container memory cap) there.
    if row["type"] != "bedrock" and mem_max < mem_min:
        return jsonify({"success": False, "message": "'mem_max' must be >= 'mem_min'"}), 400

    with get_db() as conn:
        conn.execute(
            "UPDATE servers SET mem_min_gb = ?, mem_max_gb = ? WHERE id = ?",
            (mem_min, mem_max, server_id),
        )
        updated_row = conn.execute("SELECT * FROM servers WHERE id = ?", (server_id,)).fetchone()

    try:
        docker_manager.recreate_server(updated_row)
    except Exception as exc:
        return jsonify({"success": False, "message": f"RAM updated in DB but container recreate failed: {exc}"}), 500

    log.info("Server RAM updated: db_id=%d, mem_min=%dGB, mem_max=%dGB", server_id, mem_min, mem_max)
    return jsonify({
        "success": True,
        "message": f"RAM updated: {mem_min}GB min, {mem_max}GB max. Container recreated.",
        "mem_min": mem_min,
        "mem_max": mem_max,
    }), 200


# ---------------------------------------------------------------------------
# PATCH /api/servers/<id>/version
# Body: { "version": "1.21.4", "loader_version": "RECOMMENDED" }
# ---------------------------------------------------------------------------
@servers_bp.route("/servers/<int:server_id>/version", methods=["PATCH"])
def update_server_version(server_id: int):
    """Change the Minecraft version and/or loader version. Recreates the container.

    loader_version values by type:
      forge   — "RECOMMENDED" | "LATEST" | specific e.g. "47.3.0"
      fabric  — specific e.g. "0.15.11", or omit/null for latest
      quilt   — specific version, or omit/null for latest
    """
    auth_err = authorize()
    if auth_err:
        return auth_err

    body = request.get_json(silent=True) or {}
    new_version       = body.get("version")
    has_loader        = "loader_version" in body
    new_loader        = body.get("loader_version")  # may be null to clear

    if not new_version and not has_loader:
        return jsonify({"success": False, "message": "At least 'version' or 'loader_version' is required"}), 400

    with get_db() as conn:
        row = conn.execute("SELECT * FROM servers WHERE id = ?", (server_id,)).fetchone()
    if not row:
        return jsonify({"success": False, "message": "Server not found"}), 404

    updates = {}
    if new_version:
        updates["version"] = str(new_version).strip()
    if has_loader:
        updates["loader_version"] = str(new_loader).strip() if new_loader else None

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values     = list(updates.values()) + [server_id]

    with get_db() as conn:
        conn.execute(f"UPDATE servers SET {set_clause} WHERE id = ?", values)
        updated_row = conn.execute("SELECT * FROM servers WHERE id = ?", (server_id,)).fetchone()

    try:
        docker_manager.recreate_server(updated_row)
    except Exception as exc:
        return jsonify({"success": False, "message": f"Version updated in DB but container recreate failed: {exc}"}), 500

    log.info("Server version updated: server_id=%d version=%s loader_version=%s",
             server_id, updated_row["version"], dict(updated_row).get("loader_version"))
    return jsonify({
        "success":        True,
        "message":        "Version updated, container recreated. Allow a few minutes for download.",
        "version":        updated_row["version"],
        "loader_version": dict(updated_row).get("loader_version"),
    }), 200


# ---------------------------------------------------------------------------
# PATCH /api/servers/<id>/bedrock/cheats
# Body: { "enabled": true }
#
# Bedrock-only. Sets allow-cheats in server.properties and restarts the
# container so it takes effect — allow-cheats is only read at server
# startup, there's no live console toggle for it (unlike allow-list).
# ---------------------------------------------------------------------------
@servers_bp.route("/servers/<int:server_id>/bedrock/cheats", methods=["PATCH"])
def update_bedrock_cheats(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err

    with get_db() as conn:
        row = conn.execute("SELECT type FROM servers WHERE id = ?", (server_id,)).fetchone()
    if not row:
        return jsonify({"success": False, "message": "Server not found"}), 404
    if row["type"] != "bedrock":
        return jsonify({"success": False, "message": "This endpoint is for 'bedrock' servers only"}), 400

    body = request.get_json(silent=True) or {}
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        return jsonify({"success": False, "message": "'enabled' must be a boolean"}), 400

    result = properties_manager.patch_properties(server_id, {"allow-cheats": "true" if enabled else "false"})
    if result.get("error"):
        return jsonify({"success": False, "message": result["error"]}), 404

    try:
        restart_ok, restart_msg = docker_manager.restart_server(server_id)
    except Exception as exc:
        restart_ok, restart_msg = False, str(exc)
    if not restart_ok:
        return jsonify({
            "success": False,
            "message": f"allow-cheats set to {str(enabled).lower()} but restart failed: {restart_msg}",
        }), 500

    log.info("Bedrock cheats %s: db_id=%d", "enabled" if enabled else "disabled", server_id)
    return jsonify({
        "success": True,
        "message": f"Cheats {'enabled' if enabled else 'disabled'}, server restarted",
        "enabled": enabled,
    }), 200
