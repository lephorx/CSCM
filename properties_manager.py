"""Read and edit a Minecraft server's server.properties file.

Keys that itzg/minecraft-server pins via environment variables on every
container start are blacklisted from being edited here, since a manual
edit would be silently overwritten on the next restart.
"""

import time
from pathlib import Path

from auth_manager import delete_config_value, get_config_json, set_config_json
from docker_manager import server_data_dir
from logger import get_logger

log = get_logger("properties_manager")

BLACKLISTED_KEYS = {
    "server-port",
    "enable-rcon",
    "rcon.port",
    "rcon.password",
}

DEFAULT_PROPERTIES_CONFIG_KEY = "default_server_properties"


def _properties_path(server_id: int) -> Path:
    return Path(server_data_dir(server_id)) / "server.properties"


def _normalize_properties(properties: dict) -> tuple[dict[str, str], list[str]]:
    normalized: dict[str, str] = {}
    rejected: list[str] = []
    for key, value in properties.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            rejected.append(str(key))
            continue
        if normalized_key in BLACKLISTED_KEYS:
            rejected.append(normalized_key)
            continue
        normalized[normalized_key] = str(value)
    return normalized, rejected


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


def wait_for_properties_file(server_id: int, timeout_seconds: float = 30.0, poll_interval: float = 0.5) -> Path | None:
    path = _properties_path(server_id)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.exists():
            return path
        time.sleep(poll_interval)
    return path if path.exists() else None


def get_default_properties() -> dict[str, str]:
    stored = get_config_json(DEFAULT_PROPERTIES_CONFIG_KEY, default={})
    if not isinstance(stored, dict):
        return {}
    normalized, _ = _normalize_properties(stored)
    return normalized


def set_default_properties(properties: dict) -> dict:
    normalized, rejected = _normalize_properties(properties)
    set_config_json(DEFAULT_PROPERTIES_CONFIG_KEY, normalized)
    return {"properties": normalized, "rejected": rejected}


def patch_default_properties(properties: dict) -> dict:
    current = get_default_properties()
    normalized, rejected = _normalize_properties(properties)
    current.update(normalized)
    set_config_json(DEFAULT_PROPERTIES_CONFIG_KEY, current)
    return {"properties": current, "rejected": rejected}


def delete_default_properties(keys: list[str] | None = None) -> dict:
    if not keys:
        delete_config_value(DEFAULT_PROPERTIES_CONFIG_KEY)
        return {"properties": {}}
    current = get_default_properties()
    for key in keys:
        current.pop(str(key).strip(), None)
    if current:
        set_config_json(DEFAULT_PROPERTIES_CONFIG_KEY, current)
    else:
        delete_config_value(DEFAULT_PROPERTIES_CONFIG_KEY)
    return {"properties": current}


def resolve_initial_properties(explicit_properties: dict | None = None) -> dict[str, str]:
    merged = get_default_properties()
    if explicit_properties:
        normalized, _ = _normalize_properties(explicit_properties)
        merged.update(normalized)
    return merged


def apply_initial_properties(server_id: int, explicit_properties: dict | None = None) -> dict:
    merged = resolve_initial_properties(explicit_properties)
    if not merged:
        return {"applied": False, "changed": [], "rejected": [], "restart_required": False}

    if wait_for_properties_file(server_id) is None:
        return {
            "applied": False,
            "changed": [],
            "rejected": list(merged.keys()),
            "restart_required": False,
            "warning": "server.properties was not created before the timeout elapsed",
        }

    result = patch_properties(server_id, merged)
    result["applied"] = not bool(result.get("error"))
    return result
