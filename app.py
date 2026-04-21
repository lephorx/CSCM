"""
Flask REST API for the CSCM (Crafty Server Creation Manager) Tool.

Endpoints:
    GET    /api/server-types              List supported Minecraft server types.
    GET    /api/servers                   List all provisioned servers.
    POST   /api/servers                   Provision a new server.
    DELETE /api/servers/<id>              Deprovision a server by database ID.
    POST   /api/servers/<id>/start        Start a server.
    POST   /api/servers/<id>/stop         Stop a server.
    POST   /api/servers/<id>/restart      Restart a server.
    POST   /api/servers/<id>/kill         Force-kill a server.
    POST   /api/servers/<id>/command      Send a console command to a server.
    GET    /api/servers/<id>/stats        Get a server's live stats.
    GET    /api/servers/<id>/logs         Get a server's console logs.

Authentication:
    All endpoints require an ``Authorization: Bearer <token>`` header when the
    ``API_KEY`` environment variable is set.  Omit API_KEY to disable auth
    (development only).

Environment variables:
    API_KEY      — Static bearer token for request authentication (optional).
    FLASK_HOST   — Bind address (default: 0.0.0.0).
    FLASK_PORT   — Listen port (default: 5000).
    FLASK_DEBUG  — Enable Flask debug mode; set to "true" (default: false).
    LOG_LEVEL    — Logging verbosity: DEBUG, INFO, WARNING, ERROR (default: INFO).
"""

import os
import requests
import urllib3
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from dotenv import load_dotenv

from server_manager import (
    provision_server, deprovision_server, list_servers, SERVER_TYPES,
    crafty_login, _get_db, create_server_tunnel, rename_server_subdomain,
)
from logger import get_logger, configure as configure_log

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()
configure_log()

log = get_logger("api")
app = Flask(__name__)
CORS(app)

API_KEY = os.getenv("API_KEY")


def _authorize() -> tuple | None:
    """Validate the Authorization header when API_KEY is configured.

    Returns:
        A (response, status_code) tuple when authentication fails,
        or ``None`` when the request is authorized.
    """
    if not API_KEY:
        return None
    # OPTIONS preflight requests must not be blocked — CORS headers are added
    # by flask-cors after the response is built.
    if request.method == "OPTIONS":
        return None
    if request.headers.get("Authorization") != f"Bearer {API_KEY}":
        log.warning(
            "Unauthorized request: method=%s path=%s remote=%s",
            request.method, request.path, request.remote_addr,
        )
        return jsonify({"error": "Unauthorized"}), 401
    return None


@app.before_request
def _log_request() -> None:
    log.debug(
        "Incoming request: method=%s path=%s remote=%s",
        request.method, request.path, request.remote_addr,
    )

# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health_check():
    """Basic health check endpoint."""
    return jsonify({"status": "ok", "message": "CSCM API is running"})
# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health_check_alt():
    """Alias for the health check endpoint."""
    return jsonify({"status": "ok", "message": "CSCM API is healthy"})

# ---------------------------------------------------------------------------
# GET /api/server-types
# ---------------------------------------------------------------------------
@app.route("/api/server-types", methods=["GET"])
def get_server_types():
    """Return the list of supported Minecraft server flavours."""
    auth_err = _authorize()
    if auth_err:
        return auth_err
    return jsonify({"server_types": list(SERVER_TYPES.keys())})


# ---------------------------------------------------------------------------
# GET /api/servers
# ---------------------------------------------------------------------------
@app.route("/api/servers", methods=["GET"])
def get_servers():
    """Return all provisioned servers with their tunnel and DNS details."""
    auth_err = _authorize()
    if auth_err:
        return auth_err
    servers = list_servers()
    log.info("Listed %d servers", len(servers))
    return jsonify({"servers": servers})


# ---------------------------------------------------------------------------
# POST /api/servers
#
# Request body (JSON):
#   name      string  required  Server display name.
#   type      string  optional  paper|forge|fabric|vanilla|spigot|purpur
#                               Default: paper
#   version   string  optional  Minecraft version (e.g. "1.21.4").
#                               Default: 1.21.4
#   port      int     optional  Local server port (1024-65535).
#                               Default: 25565
#   mem_min   int     optional  Minimum JVM heap in GB. Default: 2
#   mem_max   int     optional  Maximum JVM heap in GB. Default: 4
# ---------------------------------------------------------------------------
@app.route("/api/servers", methods=["POST"])
def create_server():
    """Provision a new Minecraft server stack."""
    auth_err = _authorize()
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

    version = body.get("version", "1.21.4")
    port    = body.get("port", 25565)
    mem_min = body.get("mem_min", 2)
    mem_max = body.get("mem_max", 4)

    if not isinstance(port, int) or not (1024 <= port <= 65535):
        return jsonify({"error": "'port' must be an integer between 1024 and 65535"}), 400
    if not isinstance(mem_min, int) or not isinstance(mem_max, int) \
            or mem_min < 1 or mem_max < mem_min:
        return jsonify({
            "error": "'mem_min' and 'mem_max' must be positive integers with mem_max >= mem_min"
        }), 400

    log.info(
        "Server creation requested: name=%s, type=%s, version=%s, port=%d",
        name, server_type, version, port,
    )

    result = provision_server(
        server_name=name,
        server_type=server_type,
        version=version,
        server_port=port,
        mem_min=mem_min,
        mem_max=mem_max,
    )

    if result["success"]:
        log.info("Server creation completed: db_id=%s", result.get("server_id"))
        return jsonify(result), 201
    log.error("Server creation failed: %s", result.get("message"))
    return jsonify(result), 500


# ---------------------------------------------------------------------------
# DELETE /api/servers/<id>
# ---------------------------------------------------------------------------
@app.route("/api/servers/<int:server_id>", methods=["DELETE"])
def delete_server(server_id: int):
    """Deprovision a server and all associated resources."""
    auth_err = _authorize()
    if auth_err:
        return auth_err

    log.info("Server deletion requested: db_id=%d", server_id)
    result = deprovision_server(server_id)

    if result["success"]:
        log.info("Server deletion completed: db_id=%d", server_id)
        return jsonify(result), 200
    if "No server found" in result.get("message", ""):
        return jsonify(result), 404
    log.error("Server deletion failed: %s", result.get("message"))
    return jsonify(result), 500


_base_url = os.getenv("BASE_URL", "https://localhost:8443")
_crafty_servers_dir = Path(os.getenv(
    "CRAFTY_SERVERS_DIR",
    "/var/opt/minecraft/crafty/crafty-4/servers",
))
_crafty_token: str | None = None


def _get_crafty_token() -> str | None:
    """Return the cached Crafty token, logging in only when necessary."""
    global _crafty_token
    if not _crafty_token:
        _crafty_token = crafty_login()
    return _crafty_token


def _crafty_request(method: str, path: str, **kwargs):
    """Make an authenticated request to the Crafty API, re-auth on 401."""
    token = _get_crafty_token()
    if not token:
        return None, "Could not authenticate with Crafty Controller"
    try:
        r = requests.request(
            method,
            f"{_base_url}{path}",
            headers={"Authorization": f"Bearer {token}"},
            verify=False,
            **kwargs,
        )
        if r.status_code == 401:
            # Token expired or invalidated — force re-login once
            global _crafty_token  # noqa: F811
            _crafty_token = crafty_login()
            if not _crafty_token:
                return None, "Could not re-authenticate with Crafty Controller"
            r = requests.request(
                method,
                f"{_base_url}{path}",
                headers={"Authorization": f"Bearer {_crafty_token}"},
                verify=False,
                **kwargs,
            )
        return r, None
    except requests.exceptions.RequestException as exc:
        return None, str(exc)


def _get_crafty_id(db_server_id: int):
    """Look up the Crafty server UUID for a given database server ID."""
    import psycopg2
    try:
        conn = _get_db()
        cur = conn.cursor()
        cur.execute("SELECT craftyid FROM servers WHERE id = %s", (db_server_id,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except psycopg2.Error:
        return None


# ---------------------------------------------------------------------------
# POST /api/servers/<id>/start
# ---------------------------------------------------------------------------
@app.route("/api/servers/<int:server_id>/start", methods=["POST"])
def start_server(server_id: int):
    """Start a provisioned server."""
    auth_err = _authorize()
    if auth_err:
        return auth_err
    crafty_id = _get_crafty_id(server_id)
    if not crafty_id:
        return jsonify({"success": False, "message": "Server not found"}), 404
    r, err = _crafty_request("POST", f"/api/v2/servers/{crafty_id}/action/start_server")
    if err:
        return jsonify({"success": False, "message": err}), 500
    return jsonify({"success": r.ok, "message": "Start command sent" if r.ok else r.text}), 200


# ---------------------------------------------------------------------------
# POST /api/servers/<id>/stop
# ---------------------------------------------------------------------------
@app.route("/api/servers/<int:server_id>/stop", methods=["POST"])
def stop_server(server_id: int):
    """Gracefully stop a provisioned server."""
    auth_err = _authorize()
    if auth_err:
        return auth_err
    crafty_id = _get_crafty_id(server_id)
    if not crafty_id:
        return jsonify({"success": False, "message": "Server not found"}), 404
    r, err = _crafty_request("POST", f"/api/v2/servers/{crafty_id}/action/stop_server")
    if err:
        return jsonify({"success": False, "message": err}), 500
    return jsonify({"success": r.ok, "message": "Stop command sent" if r.ok else r.text}), 200


# ---------------------------------------------------------------------------
# POST /api/servers/<id>/restart
# ---------------------------------------------------------------------------
@app.route("/api/servers/<int:server_id>/restart", methods=["POST"])
def restart_server(server_id: int):
    """Restart a provisioned server."""
    auth_err = _authorize()
    if auth_err:
        return auth_err
    crafty_id = _get_crafty_id(server_id)
    if not crafty_id:
        return jsonify({"success": False, "message": "Server not found"}), 404
    r, err = _crafty_request("POST", f"/api/v2/servers/{crafty_id}/action/restart_server")
    if err:
        return jsonify({"success": False, "message": err}), 500
    return jsonify({"success": r.ok, "message": "Restart command sent" if r.ok else r.text}), 200


# ---------------------------------------------------------------------------
# POST /api/servers/<id>/kill
# ---------------------------------------------------------------------------
@app.route("/api/servers/<int:server_id>/kill", methods=["POST"])
def kill_server(server_id: int):
    """Force-kill a provisioned server."""
    auth_err = _authorize()
    if auth_err:
        return auth_err
    crafty_id = _get_crafty_id(server_id)
    if not crafty_id:
        return jsonify({"success": False, "message": "Server not found"}), 404
    r, err = _crafty_request("POST", f"/api/v2/servers/{crafty_id}/action/kill_server")
    if err:
        return jsonify({"success": False, "message": err}), 500
    return jsonify({"success": r.ok, "message": "Kill command sent" if r.ok else r.text}), 200


# ---------------------------------------------------------------------------
# POST /api/servers/<id>/command
# Body: { "command": "say Hello" }
# ---------------------------------------------------------------------------
@app.route("/api/servers/<int:server_id>/command", methods=["POST"])
def send_command(server_id: int):
    """Send a console command to a running server."""
    auth_err = _authorize()
    if auth_err:
        return auth_err
    crafty_id = _get_crafty_id(server_id)
    if not crafty_id:
        return jsonify({"success": False, "message": "Server not found"}), 404
    body = request.get_json(silent=True) or {}
    command = body.get("command", "").strip()
    if not command:
        return jsonify({"success": False, "message": "'command' is required"}), 400
    r, err = _crafty_request(
        "POST",
        f"/api/v2/servers/{crafty_id}/stdin",
        json={"data": command},
    )
    if err:
        return jsonify({"success": False, "message": err}), 500
    return jsonify({"success": r.ok, "message": "Command sent" if r.ok else r.text}), 200


# ---------------------------------------------------------------------------
# GET /api/servers/<id>/stats
# ---------------------------------------------------------------------------
@app.route("/api/servers/<int:server_id>/stats", methods=["GET"])
def server_stats(server_id: int):
    """Get live stats for a server (running state, player count, CPU/RAM)."""
    auth_err = _authorize()
    if auth_err:
        return auth_err
    crafty_id = _get_crafty_id(server_id)
    if not crafty_id:
        return jsonify({"success": False, "message": "Server not found"}), 404
    r, err = _crafty_request("GET", f"/api/v2/servers/{crafty_id}/stats")
    if err:
        return jsonify({"success": False, "message": err}), 500
    return jsonify({"success": r.ok, "data": r.json().get("data", {})}), 200


# ---------------------------------------------------------------------------
# GET /api/servers/<id>/logs
# ---------------------------------------------------------------------------
@app.route("/api/servers/<int:server_id>/logs", methods=["GET"])
def server_logs(server_id: int):
    """Get console log output for a server."""
    auth_err = _authorize()
    if auth_err:
        return auth_err
    crafty_id = _get_crafty_id(server_id)
    if not crafty_id:
        return jsonify({"success": False, "message": "Server not found"}), 404
    r, err = _crafty_request("GET", f"/api/v2/servers/{crafty_id}/logs")
    if err:
        return jsonify({"success": False, "message": err}), 500
    return jsonify({"success": r.ok, "data": r.json().get("data", [])}), 200


# ---------------------------------------------------------------------------
# POST /api/servers/<id>/tunnel
# ---------------------------------------------------------------------------
@app.route("/api/servers/<int:server_id>/tunnel", methods=["POST"])
def create_tunnel_endpoint(server_id: int):
    """Create a PlayIT tunnel and Cloudflare DNS records for a server."""
    auth_err = _authorize()
    if auth_err:
        return auth_err

    log.info("Tunnel creation requested: db_id=%d", server_id)
    result = create_server_tunnel(server_id)

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
@app.route("/api/servers/<int:server_id>/subdomain", methods=["PATCH"])
def rename_subdomain(server_id: int):
    """Rename the Cloudflare subdomain for a server."""
    auth_err = _authorize()
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
@app.route("/api/servers/<int:server_id>/name", methods=["PATCH"])
def rename_server(server_id: int):
    """Rename a server in Crafty and the database."""
    auth_err = _authorize()
    if auth_err:
        return auth_err

    body = request.get_json(silent=True) or {}
    new_name = body.get("name", "").strip()
    if not new_name:
        return jsonify({"success": False, "message": "'name' is required"}), 400

    crafty_id = _get_crafty_id(server_id)
    if not crafty_id:
        return jsonify({"success": False, "message": "Server not found"}), 404

    r, err = _crafty_request("PATCH", f"/api/v2/servers/{crafty_id}", json={"server_name": new_name})
    if err:
        return jsonify({"success": False, "message": err}), 500
    if not r.ok:
        return jsonify({"success": False, "message": r.text}), 500

    import psycopg2
    try:
        conn = _get_db()
        cur  = conn.cursor()
        cur.execute("UPDATE servers SET name = %s WHERE id = %s", (new_name, server_id))
        conn.commit()
    except psycopg2.Error as exc:
        log.warning("DB update failed after Crafty rename: %s", exc)
    finally:
        conn.close()

    log.info("Server renamed: db_id=%d, new_name=%s", server_id, new_name)
    return jsonify({"success": True, "message": f"Server renamed to '{new_name}'"}), 200


# ---------------------------------------------------------------------------
# PATCH /api/servers/<id>/port
# Body: { "port": 25566 }
# ---------------------------------------------------------------------------
@app.route("/api/servers/<int:server_id>/port", methods=["PATCH"])
def update_server_port(server_id: int):
    """Change the server port in Crafty and the database."""
    auth_err = _authorize()
    if auth_err:
        return auth_err

    body = request.get_json(silent=True) or {}
    new_port = body.get("port")
    if not isinstance(new_port, int) or not (1024 <= new_port <= 65535):
        return jsonify({"success": False, "message": "'port' must be an integer between 1024 and 65535"}), 400

    crafty_id = _get_crafty_id(server_id)
    if not crafty_id:
        return jsonify({"success": False, "message": "Server not found"}), 404

    r, err = _crafty_request("PATCH", f"/api/v2/servers/{crafty_id}", json={"server_port": new_port})
    if err:
        return jsonify({"success": False, "message": err}), 500
    if not r.ok:
        return jsonify({"success": False, "message": r.text}), 500

    import psycopg2
    try:
        conn = _get_db()
        cur  = conn.cursor()
        cur.execute("UPDATE servers SET serverport = %s WHERE id = %s", (new_port, server_id))
        conn.commit()
    except psycopg2.Error as exc:
        log.warning("DB update failed after port change: %s", exc)
    finally:
        conn.close()

    log.info("Server port updated: db_id=%d, new_port=%d", server_id, new_port)
    return jsonify({"success": True, "message": f"Port updated to {new_port}"}), 200


# ---------------------------------------------------------------------------
# PATCH /api/servers/<id>/ram
# Body: { "mem_min": 2, "mem_max": 4 }  (values in GB)
# ---------------------------------------------------------------------------
@app.route("/api/servers/<int:server_id>/ram", methods=["PATCH"])
def update_server_ram(server_id: int):
    """Change the JVM heap allocation for a server."""
    import re
    auth_err = _authorize()
    if auth_err:
        return auth_err

    body = request.get_json(silent=True) or {}
    mem_min = body.get("mem_min")
    mem_max = body.get("mem_max")
    if not isinstance(mem_min, int) or not isinstance(mem_max, int) \
            or mem_min < 1 or mem_max < mem_min:
        return jsonify({
            "success": False,
            "message": "'mem_min' and 'mem_max' must be positive integers with mem_max >= mem_min",
        }), 400

    crafty_id = _get_crafty_id(server_id)
    if not crafty_id:
        return jsonify({"success": False, "message": "Server not found"}), 404

    # Fetch current execution_command from Crafty
    r, err = _crafty_request("GET", f"/api/v2/servers/{crafty_id}")
    if err:
        return jsonify({"success": False, "message": err}), 500
    exec_cmd = (r.json().get("data") or {}).get("execution_command", "")

    if not re.search(r"-Xms\d+[MmGg]", exec_cmd):
        return jsonify({
            "success": False,
            "message": "No -Xms/-Xmx flags found in execution command. "
                       "For Forge servers, edit user_jvm_args.txt directly.",
            "execution_command": exec_cmd,
        }), 400

    new_cmd = re.sub(r"-Xms\d+[MmGg]", f"-Xms{mem_min * 1000}M", exec_cmd)
    new_cmd = re.sub(r"-Xmx\d+[MmGg]", f"-Xmx{mem_max * 1000}M", new_cmd)

    r2, err = _crafty_request("PATCH", f"/api/v2/servers/{crafty_id}", json={"execution_command": new_cmd})
    if err:
        return jsonify({"success": False, "message": err}), 500
    if not r2.ok:
        return jsonify({"success": False, "message": r2.text}), 500

    log.info("Server RAM updated: db_id=%d, mem_min=%dGB, mem_max=%dGB", server_id, mem_min, mem_max)
    return jsonify({
        "success": True,
        "message": f"RAM updated: {mem_min}GB min, {mem_max}GB max",
        "execution_command": new_cmd,
    }), 200


def _server_dir(crafty_id: str, rel_path: str = "") -> Path | None:
    """Resolve a path inside a server's directory, guarding against traversal."""
    base = (_crafty_servers_dir / crafty_id).resolve()
    rel_path = rel_path.lstrip("/")
    target = (base / rel_path).resolve() if rel_path else base
    if not str(target).startswith(str(base)):
        return None  # path traversal attempt
    return target


# ---------------------------------------------------------------------------
# GET /api/servers/<id>/files?path=subdir/...
# ---------------------------------------------------------------------------
@app.route("/api/servers/<int:server_id>/files", methods=["GET"])
def list_files(server_id: int):
    """List files and directories inside a server's folder."""
    auth_err = _authorize()
    if auth_err:
        return auth_err
    crafty_id = _get_crafty_id(server_id)
    if not crafty_id:
        return jsonify({"success": False, "message": "Server not found"}), 404

    rel_path = request.args.get("path", "")
    target = _server_dir(crafty_id, rel_path)
    if target is None:
        return jsonify({"success": False, "message": "Invalid path"}), 400
    if not target.exists():
        return jsonify({"success": False, "message": "Path does not exist"}), 404
    if not target.is_dir():
        return jsonify({"success": False, "message": "Path is not a directory"}), 400

    entries = []
    for entry in sorted(target.iterdir(), key=lambda e: (e.is_file(), e.name)):
        entries.append({
            "name": entry.name,
            "type": "file" if entry.is_file() else "directory",
            "size": entry.stat().st_size if entry.is_file() else None,
        })
    return jsonify({"success": True, "path": rel_path or "/", "entries": entries}), 200


# ---------------------------------------------------------------------------
# GET /api/servers/<id>/files/download?path=file.txt
# ---------------------------------------------------------------------------
@app.route("/api/servers/<int:server_id>/files/download", methods=["GET"])
def download_file(server_id: int):
    """Download a file from a server's folder."""
    auth_err = _authorize()
    if auth_err:
        return auth_err
    crafty_id = _get_crafty_id(server_id)
    if not crafty_id:
        return jsonify({"success": False, "message": "Server not found"}), 404

    rel_path = request.args.get("path", "")
    if not rel_path:
        return jsonify({"success": False, "message": "'path' query parameter is required"}), 400
    target = _server_dir(crafty_id, rel_path)
    if target is None:
        return jsonify({"success": False, "message": "Invalid path"}), 400
    if not target.exists() or not target.is_file():
        return jsonify({"success": False, "message": "File not found"}), 404

    return send_file(target, as_attachment=True, download_name=target.name)


# ---------------------------------------------------------------------------
# POST /api/servers/<id>/files/upload?path=subdir/...
# Body: multipart/form-data with field "file"
# ---------------------------------------------------------------------------
@app.route("/api/servers/<int:server_id>/files/upload", methods=["POST"])
def upload_file(server_id: int):
    """Upload a file into a server's folder (or subfolder via ?path=)."""
    auth_err = _authorize()
    if auth_err:
        return auth_err
    crafty_id = _get_crafty_id(server_id)
    if not crafty_id:
        return jsonify({"success": False, "message": "Server not found"}), 404

    if "file" not in request.files:
        return jsonify({"success": False, "message": "No file field in request"}), 400

    upload = request.files["file"]
    if not upload.filename:
        return jsonify({"success": False, "message": "Empty filename"}), 400

    # Sanitise filename — strip directory components
    filename = Path(upload.filename).name
    rel_path = request.args.get("path", "")
    target_dir = _server_dir(crafty_id, rel_path)
    if target_dir is None:
        return jsonify({"success": False, "message": "Invalid path"}), 400

    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / filename
    upload.save(dest)
    log.info("File uploaded: server_id=%d path=%s", server_id, dest)
    return jsonify({"success": True, "message": f"Uploaded {filename}", "path": str(dest)}), 201


# ---------------------------------------------------------------------------
# DELETE /api/servers/<id>/files?path=file.txt
# ---------------------------------------------------------------------------
@app.route("/api/servers/<int:server_id>/files/delete", methods=["DELETE"])
def delete_file(server_id: int):
    """Delete a file from a server's folder."""
    auth_err = _authorize()
    if auth_err:
        return auth_err
    crafty_id = _get_crafty_id(server_id)
    if not crafty_id:
        return jsonify({"success": False, "message": "Server not found"}), 404

    rel_path = request.args.get("path", "")
    if not rel_path:
        return jsonify({"success": False, "message": "'path' query parameter is required"}), 400
    target = _server_dir(crafty_id, rel_path)
    if target is None:
        return jsonify({"success": False, "message": "Invalid path"}), 400
    if not target.exists():
        return jsonify({"success": False, "message": "File not found"}), 404
    if target.is_dir():
        return jsonify({"success": False, "message": "Path is a directory, not a file"}), 400

    target.unlink()
    log.info("File deleted: server_id=%d path=%s", server_id, target)
    return jsonify({"success": True, "message": f"Deleted {target.name}"}), 200


if __name__ == "__main__":
    host  = os.getenv("FLASK_HOST", "0.0.0.0")
    port  = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    log.info("Starting CSCM API on %s:%d (debug=%s)", host, port, debug)
    app.run(host=host, port=port, debug=debug)
