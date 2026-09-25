"""Shared JWT bearer-token authorization helper for all route blueprints.

Kept separate from app.py to avoid circular imports between the app factory
and the blueprints it registers.
"""

from flask import g, jsonify, request

from auth_manager import has_users, verify_jwt
from logger import get_logger

log = get_logger("api")


def extract_bearer_token() -> str | None:
    authorization = request.headers.get("Authorization", "").strip()
    if not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    # Guard against double-prefixed tokens ("Bearer Bearer eyJ...")
    if token.startswith("Bearer "):
        token = token[7:].strip()
    return token or None


def authorize() -> tuple | None:
    """Validate a JWT bearer token for protected API routes.

    On success, sets g.current_user and returns None.
    On failure, returns a (response, status_code) tuple to return directly.
    """
    if request.method == "OPTIONS":
        return None
    if not has_users():
        return jsonify({"error": "Setup required", "setup_required": True}), 403

    token = extract_bearer_token()
    if not token:
        log.warning(
            "Missing bearer token: method=%s path=%s remote=%s",
            request.method, request.path, request.remote_addr,
        )
        return jsonify({"error": "Unauthorized"}), 401

    user = verify_jwt(token)
    if not user:
        log.warning(
            "Unauthorized request: method=%s path=%s remote=%s",
            request.method, request.path, request.remote_addr,
        )
        return jsonify({"error": "Unauthorized"}), 401
    g.current_user = user
    return None
