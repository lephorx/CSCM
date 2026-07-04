"""File management endpoints, operating directly on a server's data directory."""

from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

from auth_helpers import authorize
from db import get_db
from docker_manager import server_data_dir
from logger import get_logger

log = get_logger("api")

files_bp = Blueprint("files", __name__, url_prefix="/api")


def _server_exists(server_id: int) -> bool:
    with get_db() as conn:
        return conn.execute("SELECT 1 FROM servers WHERE id = ?", (server_id,)).fetchone() is not None


def _server_dir(server_id: int, rel_path: str = "") -> Path | None:
    """Resolve a path inside a server's data directory, guarding against traversal."""
    base = Path(server_data_dir(server_id)).resolve()
    rel_path = rel_path.lstrip("/")
    target = (base / rel_path).resolve() if rel_path else base
    if not str(target).startswith(str(base)):
        return None  # path traversal attempt
    return target


def _upload_destination(
    server_id: int,
    rel_path: str,
    original_filename: str,
    requested_filename: str | None = None,
) -> tuple[Path, Path] | tuple[None, None]:
    rel_path = rel_path.strip()
    filename = Path(requested_filename or original_filename).name
    if not rel_path:
        target_dir = _server_dir(server_id, "")
        return target_dir, target_dir / filename if target_dir else (None, None)

    target = _server_dir(server_id, rel_path)
    if target is None:
        return None, None

    if requested_filename:
        return target, target / filename

    if target.exists() and target.is_file():
        parent_dir = _server_dir(server_id, str(rel.parent) if str(rel.parent) != "." else "")
        if parent_dir is None:
            return None, None
        return parent_dir, target

    return target, target / filename


# ---------------------------------------------------------------------------
# GET /api/servers/<id>/files?path=subdir/...
# ---------------------------------------------------------------------------
@files_bp.route("/servers/<int:server_id>/files", methods=["GET"])
def list_files(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err
    if not _server_exists(server_id):
        return jsonify({"success": False, "message": "Server not found"}), 404

    rel_path = request.args.get("path", "")
    target = _server_dir(server_id, rel_path)
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
@files_bp.route("/servers/<int:server_id>/files/download", methods=["GET"])
def download_file(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err
    if not _server_exists(server_id):
        return jsonify({"success": False, "message": "Server not found"}), 404

    rel_path = request.args.get("path", "")
    if not rel_path:
        return jsonify({"success": False, "message": "'path' query parameter is required"}), 400
    target = _server_dir(server_id, rel_path)
    if target is None:
        return jsonify({"success": False, "message": "Invalid path"}), 400
    if not target.exists() or not target.is_file():
        return jsonify({"success": False, "message": "File not found"}), 404

    return send_file(target, as_attachment=True, download_name=target.name)


# ---------------------------------------------------------------------------
# POST /api/servers/<id>/files/upload?path=subdir/...
# Body: multipart/form-data with field "file"
# ---------------------------------------------------------------------------
@files_bp.route("/servers/<int:server_id>/files/upload", methods=["POST"])
def upload_file(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err
    if not _server_exists(server_id):
        return jsonify({"success": False, "message": "Server not found"}), 404

    if "file" not in request.files:
        return jsonify({"success": False, "message": "No file field in request"}), 400

    upload = request.files["file"]
    if not upload.filename:
        return jsonify({"success": False, "message": "Empty filename"}), 400

    # Sanitise filename — strip directory components
    filename = Path(upload.filename).name
    rel_path = request.args.get("path", "")
    requested_filename = request.args.get("filename", "").strip() or None
    target_dir, dest = _upload_destination(server_id, rel_path, filename, requested_filename)
    if target_dir is None or dest is None:
        return jsonify({"success": False, "message": "Invalid path"}), 400

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        upload.save(dest)
    except OSError as exc:
        log.warning("File upload failed: server_id=%d path=%s error=%s", server_id, dest, exc)
        return jsonify({"success": False, "message": f"Could not save upload: {exc}"}), 500

    log.info("File uploaded: server_id=%d path=%s", server_id, dest)
    return jsonify({"success": True, "message": f"Uploaded {filename}", "path": str(dest)}), 201


# ---------------------------------------------------------------------------
# DELETE /api/servers/<id>/files/delete?path=file.txt
# ---------------------------------------------------------------------------
@files_bp.route("/servers/<int:server_id>/files/delete", methods=["DELETE"])
def delete_file(server_id: int):
    auth_err = authorize()
    if auth_err:
        return auth_err
    if not _server_exists(server_id):
        return jsonify({"success": False, "message": "Server not found"}), 404

    rel_path = request.args.get("path", "")
    if not rel_path:
        return jsonify({"success": False, "message": "'path' query parameter is required"}), 400
    target = _server_dir(server_id, rel_path)
    if target is None:
        return jsonify({"success": False, "message": "Invalid path"}), 400
    if not target.exists():
        return jsonify({"success": False, "message": "File not found"}), 404
    if target.is_dir():
        return jsonify({"success": False, "message": "Path is a directory, not a file"}), 400

    target.unlink()
    log.info("File deleted: server_id=%d path=%s", server_id, target)
    return jsonify({"success": True, "message": f"Deleted {target.name}"}), 200
