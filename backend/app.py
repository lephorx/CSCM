"""Flask REST API for CSCM with local-user JWT and TOTP auth.

Server lifecycle (create/start/stop/console/stats/etc.) is handled natively
via Docker (see docker_manager.py) — no external Crafty Controller. App data
lives in a local SQLite database (see db.py).
"""

import os
from pathlib import Path

from docker.errors import DockerException
from flask import Flask, g, jsonify, request
from dotenv import load_dotenv

import backup_manager
from auth_helpers import authorize, extract_bearer_token
from auth_manager import (
    authenticate_user,
    begin_initial_user_setup,
    complete_initial_user_setup,
    has_users,
    initialize_auth_storage,
    issue_jwt,
    verify_jwt,
)
from db import init_schema
from logger import get_logger, configure as configure_log
from routes.backups import backups_bp
from routes.console import console_bp
from routes.files import files_bp
from routes.players import players_bp
from routes.properties import properties_bp
from routes.servers import servers_bp
from routes.settings import settings_bp
from routes.system import system_bp

load_dotenv()
configure_log()

log = get_logger("api")
app = Flask(__name__)

init_schema()
initialize_auth_storage()


def _validate_server_dirs() -> None:
    """Fail fast if SERVERS_DIR / BACKUPS_DIR are not writable from this process.

    This catches the most common misconfiguration: SERVERS_DIR_HOST pointing
    at a different physical location than SERVERS_DIR (see .env.example).
    """
    for env_var, default in (("SERVERS_DIR", "/data/servers"), ("BACKUPS_DIR", "/data/backups")):
        path = Path(os.getenv(env_var, default))
        path.mkdir(parents=True, exist_ok=True)
        marker = path / ".cscm-write-check"
        try:
            marker.write_text("ok")
            marker.unlink()
        except OSError as exc:
            raise RuntimeError(f"{env_var}={path} is not writable by the management process: {exc}") from exc


_validate_server_dirs()
backup_manager.init_scheduler()

app.register_blueprint(servers_bp)
app.register_blueprint(files_bp)
app.register_blueprint(console_bp)
app.register_blueprint(properties_bp)
app.register_blueprint(players_bp)
app.register_blueprint(backups_bp)
app.register_blueprint(system_bp)
app.register_blueprint(settings_bp)


@app.before_request
def _log_request() -> None:
    log.debug(
        "Incoming request: method=%s path=%s remote=%s",
        request.method, request.path, request.remote_addr,
    )


@app.errorhandler(DockerException)
def handle_docker_unavailable(exc: DockerException):
    """Nearly every route touches docker_manager, which talks to the Docker
    daemon over its socket. Without this, an unreachable daemon (not
    running, crashed, socket permissions) surfaces as a raw Python
    traceback on whichever endpoint happened to hit it first, instead of a
    single clean, consistent error.
    """
    log.error("Docker daemon unavailable: method=%s path=%s error=%s", request.method, request.path, exc)
    return jsonify({
        "success": False,
        "message": f"Docker daemon unavailable — is it running? ({exc})",
    }), 503


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    """Identify the internal API; the dashboard serves the user interface."""
    return jsonify({"name": "CSCM API", "health": "/health"})


# ---------------------------------------------------------------------------
# GET /api/auth/status
# ---------------------------------------------------------------------------
@app.route("/api/auth/status", methods=["GET"])
def auth_status():
    """Return whether initial setup is required and whether the caller is authenticated."""
    token = extract_bearer_token()
    current_user = verify_jwt(token) if token else None
    return jsonify({
        "setup_required": not has_users(),
        "authenticated": current_user is not None,
        "user": current_user,
    })


# ---------------------------------------------------------------------------
# POST /api/auth/setup
# ---------------------------------------------------------------------------
@app.route("/api/auth/setup", methods=["POST"])
def setup_auth():
    """Start enrollment without creating the administrator account yet."""
    if has_users():
        return jsonify({"error": "Initial setup has already been completed"}), 409

    body = request.get_json(silent=True) or {}
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))

    try:
        setup_payload = begin_initial_user_setup(username, password)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409

    log.info("Initial account setup started: username=%s", username)
    return jsonify({
        "success": True,
        "message": "Scan the QR code, then enter a one-time code to finish registration.",
        **setup_payload,
    }), 202


@app.route("/api/auth/setup/verify", methods=["POST"])
def verify_setup():
    """Verify the first TOTP code and create the administrator atomically."""
    body = request.get_json(silent=True) or {}
    setup_token = str(body.get("setup_token", ""))
    otp_code = str(body.get("otp", "")).strip()

    try:
        user = complete_initial_user_setup(setup_token, otp_code)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409

    token, expires_at = issue_jwt(user["id"], user["username"])
    log.info("Initial account verified and created: username=%s", user["username"])
    return jsonify({
        "success": True,
        "token": token,
        "token_type": "Bearer",
        "expires_at": expires_at,
        "user": user,
    }), 201


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------
@app.route("/api/auth/login", methods=["POST"])
def login():
    """Authenticate a local user with username, password, and TOTP."""
    if not has_users():
        return jsonify({"error": "Setup required", "setup_required": True}), 403

    body = request.get_json(silent=True) or {}
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    otp_code = str(body.get("otp", "")).strip()

    if not username or not password or not otp_code:
        return jsonify({"error": "'username', 'password', and 'otp' are required"}), 400

    user = authenticate_user(username, password, otp_code)
    if not user:
        log.warning("Failed login for username=%s", username)
        return jsonify({"error": "Invalid username, password, or one-time password"}), 401

    token, expires_at = issue_jwt(user["id"], user["username"])
    log.info("User logged in: username=%s", user["username"])
    return jsonify({
        "success": True,
        "token": token,
        "token_type": "Bearer",
        "expires_at": expires_at,
        "user": user,
    })


# ---------------------------------------------------------------------------
# GET /api/auth/me
# ---------------------------------------------------------------------------
@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    """Return the authenticated user for the supplied JWT."""
    auth_err = authorize()
    if auth_err:
        return auth_err
    return jsonify({"authenticated": True, "user": g.current_user})


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health_check_alt():
    """Alias for the health check endpoint."""
    return jsonify({"status": "ok", "message": "CSCM API is healthy"})


if __name__ == "__main__":
    host  = os.getenv("FLASK_HOST", "0.0.0.0")
    port  = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    log.info("Starting CSCM API on %s:%d (debug=%s)", host, port, debug)
    app.run(host=host, port=port, debug=debug, threaded=True)
