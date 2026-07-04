"""Live console log streaming via Server-Sent Events (SSE)."""

import time

from flask import Blueprint, Response, jsonify, request, stream_with_context

import docker_manager
from auth_manager import verify_jwt
from db import get_db
from logger import get_logger

log = get_logger("api")

console_bp = Blueprint("console", __name__, url_prefix="/api")


def _server_exists(server_id: int) -> bool:
    with get_db() as conn:
        return conn.execute("SELECT 1 FROM servers WHERE id = ?", (server_id,)).fetchone() is not None


@console_bp.route("/servers/<int:server_id>/console/stream", methods=["GET"])
def stream_console(server_id: int):
    """SSE stream of live console output.

    EventSource cannot set custom headers, so the JWT is passed as a query
    parameter here instead of an Authorization header.
    """
    token = request.args.get("token", "")
    user = verify_jwt(token) if token else None
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    if not _server_exists(server_id):
        return jsonify({"success": False, "message": "Server not found"}), 404

    def event_stream():
        last_keepalive = time.time()
        try:
            for line in docker_manager.stream_logs(server_id):
                yield f"event: log\ndata: {line}\n\n"
                if time.time() - last_keepalive > 15:
                    yield ": keepalive\n\n"
                    last_keepalive = time.time()
        except GeneratorExit:
            return

    response = Response(stream_with_context(event_stream()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response
