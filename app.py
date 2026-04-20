"""
Flask REST API for the CSCM (Crafty Server Creation Manager) Tool.

Endpoints:
    GET    /api/server-types        List supported Minecraft server types.
    GET    /api/servers             List all provisioned servers.
    POST   /api/servers             Provision a new server.
    DELETE /api/servers/<id>        Deprovision a server by database ID.

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
from flask import Flask, request, jsonify
from dotenv import load_dotenv

from server_manager import provision_server, deprovision_server, list_servers, SERVER_TYPES
from logger import get_logger, configure as configure_log

load_dotenv()
configure_log()

log = get_logger("api")
app = Flask(__name__)

API_KEY = os.getenv("API_KEY")


def _authorize() -> tuple | None:
    """Validate the Authorization header when API_KEY is configured.

    Returns:
        A (response, status_code) tuple when authentication fails,
        or ``None`` when the request is authorized.
    """
    if not API_KEY:
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


if __name__ == "__main__":
    host  = os.getenv("FLASK_HOST", "0.0.0.0")
    port  = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    log.info("Starting CSCM API on %s:%d (debug=%s)", host, port, debug)
    app.run(host=host, port=port, debug=debug)
