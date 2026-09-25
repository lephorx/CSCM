"""Version check and one-click update routes."""

from flask import Blueprint, jsonify, request

import update_manager
from auth_helpers import authorize
from logger import get_logger

log = get_logger("api")

system_bp = Blueprint("system", __name__, url_prefix="/api/system")


# ---------------------------------------------------------------------------
# GET /api/system/version[?refresh=1]
# ---------------------------------------------------------------------------
@system_bp.route("/version", methods=["GET"])
def version():
    auth_err = authorize()
    if auth_err:
        return auth_err

    current = update_manager.current_version()
    latest, error = update_manager.latest_version(force=request.args.get("refresh") == "1")
    _, reason = update_manager.install_info()
    return jsonify({
        "current": current,
        "latest": latest,
        "update_available": bool(latest) and update_manager.is_newer(latest, current),
        "can_update": reason is None,
        "reason": reason,
        "check_error": error,
    })


# ---------------------------------------------------------------------------
# POST /api/system/update  — starts the update helper
# GET  /api/system/update  — progress of the running / last update
# ---------------------------------------------------------------------------
@system_bp.route("/update", methods=["POST"])
def start_update():
    auth_err = authorize()
    if auth_err:
        return auth_err

    try:
        ok, message = update_manager.start_update()
    except Exception as exc:
        log.exception("Could not start update")
        return jsonify({"success": False, "message": f"Could not start the update: {exc}"}), 500
    return jsonify({"success": ok, "message": message}), (202 if ok else 409)


@system_bp.route("/update", methods=["GET"])
def update_status():
    auth_err = authorize()
    if auth_err:
        return auth_err
    return jsonify(update_manager.status())
