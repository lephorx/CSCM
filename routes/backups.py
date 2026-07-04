"""Backup create/list/restore/delete and schedule management routes."""

from flask import Blueprint, jsonify, request

import backup_manager
from auth_helpers import authorize
from db import get_db
from logger import get_logger

log = get_logger("api")

backups_bp = Blueprint("backups", __name__, url_prefix="/api")


def _server_exists(server_id: int) -> bool:
    with get_db() as conn:
        return conn.execute("SELECT 1 FROM servers WHERE id = ?", (server_id,)).fetchone() is not None


def _require_server(server_id: int):
    if not _server_exists(server_id):
        return jsonify({"success": False, "message": "Server not found"}), 404
    return None


@backups_bp.route("/servers/<int:server_id>/backups", methods=["GET"])
def list_backups(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err
    err = _require_server(server_id)
    if err:
        return err
    return jsonify({"success": True, "backups": backup_manager.list_backups(server_id)}), 200


@backups_bp.route("/servers/<int:server_id>/backups", methods=["POST"])
def create_backup(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err
    err = _require_server(server_id)
    if err:
        return err
    result = backup_manager.create_backup(server_id, kind="manual")
    return jsonify(result), 201 if result["success"] else 500


@backups_bp.route("/servers/<int:server_id>/backups/<int:backup_id>", methods=["DELETE"])
def delete_backup(server_id: int, backup_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err
    err = _require_server(server_id)
    if err:
        return err
    result = backup_manager.delete_backup(server_id, backup_id)
    return jsonify(result), 200 if result["success"] else 404


@backups_bp.route("/servers/<int:server_id>/backups/<int:backup_id>/restore", methods=["POST"])
def restore_backup(server_id: int, backup_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err
    err = _require_server(server_id)
    if err:
        return err
    result = backup_manager.restore_backup(server_id, backup_id)
    return jsonify(result), 200 if result["success"] else 500


@backups_bp.route("/servers/<int:server_id>/backups/schedule", methods=["GET"])
def get_schedule(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err
    err = _require_server(server_id)
    if err:
        return err
    schedule = backup_manager.get_schedule(server_id)
    if not schedule:
        return jsonify({"success": True, "schedule": None}), 200
    return jsonify({"success": True, "schedule": schedule}), 200


@backups_bp.route("/servers/<int:server_id>/backups/schedule", methods=["PUT"])
def set_schedule(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err
    err = _require_server(server_id)
    if err:
        return err

    body = request.get_json(silent=True) or {}
    cron = body.get("cron", "").strip()
    if not cron:
        return jsonify({"success": False, "message": "'cron' is required (5-field crontab expression)"}), 400
    retention = body.get("retention", 5)
    enabled = body.get("enabled", True)
    if not isinstance(retention, int) or retention < 1:
        return jsonify({"success": False, "message": "'retention' must be a positive integer"}), 400

    result = backup_manager.set_schedule(server_id, cron, retention, bool(enabled))
    return jsonify(result), 200 if result["success"] else 400


@backups_bp.route("/servers/<int:server_id>/backups/schedule", methods=["DELETE"])
def delete_schedule(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err
    err = _require_server(server_id)
    if err:
        return err
    result = backup_manager.delete_schedule(server_id)
    return jsonify(result), 200
