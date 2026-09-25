"""Connection settings and first-run setup routes (all require a login)."""

from flask import Blueprint, jsonify, request

import settings_manager
from auth_helpers import authorize
from logger import get_logger

log = get_logger("api")

settings_bp = Blueprint("settings", __name__, url_prefix="/api")


# ---------------------------------------------------------------------------
# GET /api/settings  — current values; secrets are only reported as set/unset
# PUT /api/settings  — body: { "values": { "PLAYIT_EMAIL": "...", ... } }
#                      null or missing = unchanged, "" = clear
# ---------------------------------------------------------------------------
@settings_bp.route("/settings", methods=["GET"])
def get_settings():
    auth_err = authorize()
    if auth_err:
        return auth_err
    return jsonify({**settings_manager.public_view(), "setup": settings_manager.setup_state()})


@settings_bp.route("/settings", methods=["PUT"])
def put_settings():
    auth_err = authorize()
    if auth_err:
        return auth_err
    body = request.get_json(silent=True) or {}
    values = body.get("values") or {}
    if not isinstance(values, dict) or not all(isinstance(v, (str, type(None))) for v in values.values()):
        return jsonify({"success": False, "message": "'values' must map keys to strings"}), 400
    unknown = sorted(set(values) - set(settings_manager.EDITABLE_KEYS))
    if unknown:
        return jsonify({"success": False, "message": f"Unknown settings: {', '.join(unknown)}"}), 400
    try:
        settings_manager.save(values)
    except (RuntimeError, ValueError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 409
    return jsonify({"success": True, **settings_manager.public_view(), "setup": settings_manager.setup_state()})


# ---------------------------------------------------------------------------
# POST   /api/settings/agent — start the Playit agent with the saved SECRET_KEY
# DELETE /api/settings/agent — remove it
# ---------------------------------------------------------------------------
@settings_bp.route("/settings/agent", methods=["POST"])
def start_agent():
    auth_err = authorize()
    if auth_err:
        return auth_err
    try:
        settings_manager.start_agent()
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        log.exception("Could not start the Playit agent")
        return jsonify({"success": False, "message": f"Could not start the Playit agent: {exc}"}), 500
    return jsonify({"success": True, "agent": settings_manager.agent_status()})


@settings_bp.route("/settings/agent", methods=["DELETE"])
def stop_agent():
    auth_err = authorize()
    if auth_err:
        return auth_err
    settings_manager.stop_agent()
    return jsonify({"success": True, "agent": settings_manager.agent_status()})


# ---------------------------------------------------------------------------
# GET /api/setup — wizard progress
# PUT /api/setup — body: { "step"?: "...", "mode"?: "public"|"local", "completed"?: bool }
# ---------------------------------------------------------------------------
@settings_bp.route("/setup", methods=["GET"])
def get_setup():
    auth_err = authorize()
    if auth_err:
        return auth_err
    return jsonify(settings_manager.setup_state())


@settings_bp.route("/setup", methods=["PUT"])
def put_setup():
    auth_err = authorize()
    if auth_err:
        return auth_err
    body = request.get_json(silent=True) or {}
    state = settings_manager.update_setup(
        step=body.get("step"),
        mode=body.get("mode"),
        completed=body.get("completed"),
    )
    return jsonify(state)
