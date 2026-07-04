"""Read and edit a Minecraft server's server.properties file.

Keys that itzg/minecraft-server pins via environment variables on every
container start are blacklisted from being edited here, since a manual
edit would be silently overwritten on the next restart.
"""

from pathlib import Path

from docker_manager import server_data_dir
from logger import get_logger

log = get_logger("properties_manager")

BLACKLISTED_KEYS = {
    "server-port",
    "enable-rcon",
    "rcon.port",
    "rcon.password",
}


def _properties_path(server_id: int) -> Path:
    return Path(server_data_dir(server_id)) / "server.properties"


def read_properties(server_id: int) -> dict:
    path = _properties_path(server_id)
    if not path.exists():
        return {}
    props = {}
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        props[key.strip()] = value.strip()
    return props


def patch_properties(server_id: int, changes: dict) -> dict:
    """Apply key/value changes to server.properties, preserving comments/order.

    Returns {"changed": [...], "rejected": [...], "restart_required": bool}.
    """
    path = _properties_path(server_id)
    if not path.exists():
        return {"changed": [], "rejected": list(changes.keys()), "restart_required": False,
                 "error": "server.properties not found — has the server started at least once?"}

    lines = path.read_text(errors="replace").splitlines()
    remaining = dict(changes)
    changed = []
    rejected = []

    for key in list(remaining.keys()):
        if key in BLACKLISTED_KEYS:
            rejected.append(key)
            remaining.pop(key)

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, _ = stripped.partition("=")
        key = key.strip()
        if key in remaining:
            lines[i] = f"{key}={remaining.pop(key)}"
            changed.append(key)

    # Any keys not already present in the file get appended.
    for key, value in remaining.items():
        lines.append(f"{key}={value}")
        changed.append(key)

    path.write_text("\n".join(lines) + "\n")
    log.info("server.properties updated: server_id=%d, changed=%s", server_id, changed)
    return {"changed": changed, "rejected": rejected, "restart_required": bool(changed)}
