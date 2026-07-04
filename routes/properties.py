"""server.properties viewer/editor routes."""

from flask import Blueprint, jsonify, request

import properties_manager
from auth_helpers import authorize
from db import get_db
from logger import get_logger

log = get_logger("api")

properties_bp = Blueprint("properties", __name__, url_prefix="/api")


def _server_exists(server_id: int) -> bool:
    with get_db() as conn:
        return conn.execute("SELECT 1 FROM servers WHERE id = ?", (server_id,)).fetchone() is not None


@properties_bp.route("/defaults/properties", methods=["GET"])
def get_default_properties():
    auth_err = authorize()
    if auth_err:
        return auth_err
    return jsonify({"success": True, "properties": properties_manager.get_default_properties()}), 200


@properties_bp.route("/defaults/properties", methods=["PUT"])
def put_default_properties():
    auth_err = authorize()
    if auth_err:
        return auth_err
    body = request.get_json(silent=True) or {}
    changes = body.get("properties")
    if not isinstance(changes, dict):
        return jsonify({"success": False, "message": "'properties' must be an object"}), 400
    result = properties_manager.set_default_properties(changes)
    return jsonify({"success": True, **result}), 200


@properties_bp.route("/defaults/properties", methods=["PATCH"])
def patch_default_properties():
    auth_err = authorize()
    if auth_err:
        return auth_err
    body = request.get_json(silent=True) or {}
    changes = body.get("properties")
    if not isinstance(changes, dict) or not changes:
        return jsonify({"success": False, "message": "'properties' must be a non-empty object"}), 400
    result = properties_manager.patch_default_properties(changes)
    return jsonify({"success": True, **result}), 200


@properties_bp.route("/defaults/properties", methods=["DELETE"])
def remove_default_properties():
    auth_err = authorize()
    if auth_err:
        return auth_err
    body = request.get_json(silent=True) or {}
    keys = body.get("keys")
    if keys is not None and not isinstance(keys, list):
        return jsonify({"success": False, "message": "'keys' must be a list when provided"}), 400
    result = properties_manager.delete_default_properties(keys)
    return jsonify({"success": True, **result}), 200


@properties_bp.route("/servers/<int:server_id>/properties", methods=["GET"])
def get_properties(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err
    if not _server_exists(server_id):
        return jsonify({"success": False, "message": "Server not found"}), 404

    props = properties_manager.read_properties(server_id)
    return jsonify({"success": True, "properties": props}), 200


@properties_bp.route("/servers/<int:server_id>/properties", methods=["PATCH"])
def patch_properties(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err
    if not _server_exists(server_id):
        return jsonify({"success": False, "message": "Server not found"}), 404

    body = request.get_json(silent=True) or {}
    changes = body.get("properties")
    if not isinstance(changes, dict) or not changes:
        return jsonify({"success": False, "message": "'properties' must be a non-empty object"}), 400

    result = properties_manager.patch_properties(server_id, {str(k): str(v) for k, v in changes.items()})
    if result.get("error"):
        return jsonify({"success": False, "message": result["error"]}), 404
    return jsonify({"success": True, **result}), 200
