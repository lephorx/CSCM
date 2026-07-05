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
    "server-portv6",  # Bedrock IPv6 port — also env-pinned
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


# ── Bedrock-specific server.properties ──────────────────────────────────────
# Bedrock's server.properties key set barely overlaps with Java's (e.g.
# "allow-cheats", "level-type", "server-authoritative-movement" don't exist
# on Java; Java's "motd"/"pvp"/"spawn-protection" don't exist on Bedrock), so
# it gets its own validated key list instead of sharing Java's free-form
# patch_properties. Source: itzg/docker-minecraft-bedrock-server's
# property-definitions.json (verified against the actual image, 2026-07).

BEDROCK_PROPERTY_ALLOWED_VALUES: dict[str, list[str]] = {
    "gamemode": ["survival", "creative", "adventure"],
    "force-gamemode": ["true", "false"],
    "difficulty": ["peaceful", "easy", "normal", "hard"],
    "allow-cheats": ["true", "false"],
    "online-mode": ["true", "false"],
    "white-list": ["true", "false"],  # deprecated by Bedrock — prefer allow-list
    "allow-list": ["true", "false"],
    "enable-lan-visibility": ["true", "false"],
    "level-type": ["DEFAULT", "FLAT", "LEGACY"],
    "default-player-permission-level": ["visitor", "member", "operator"],
    "texturepack-required": ["true", "false"],
    "content-log-file-enabled": ["true", "false"],
    "content-log-level": ["verbose", "info", "warning", "error"],
    "content-log-console-output-enabled": ["true", "false"],
    "compression-algorithm": ["zlib", "snappy"],
    "server-authoritative-movement": ["server-auth", "client-auth", "server-auth-with-rewind"],
    "correct-player-movement": ["true", "false"],
    "server-authoritative-block-breaking": ["true", "false"],
    "chat-restriction": ["None", "Dropped", "Disabled"],
    "disable-player-interaction": ["true", "false"],
    "client-side-chunk-generation-enabled": ["true", "false"],
    "block-network-ids-are-hashes": ["true", "false"],
    "disable-persona": ["true", "false"],
    "disable-custom-skins": ["true", "false"],
    "allow-outbound-script-debugging": ["true", "false"],
    "allow-inbound-script-debugging": ["true", "false"],
    "script-debugger-auto-attach": ["disabled", "connect", "listen"],
    "script-watchdog-enable": ["true", "false"],
    "script-watchdog-enable-exception-handling": ["true", "false"],
    "script-watchdog-enable-shutdown": ["true", "false"],
    "script-watchdog-hang-exception": ["true", "false"],
    "emit-server-telemetry": ["true", "false"],
    "msa-gamertags-only": ["true", "false"],
    "item-transaction-logging-enabled": ["true", "false"],
}

# Valid Bedrock keys with no fixed allowed-value set (free-form strings/numbers).
BEDROCK_FREEFORM_KEYS = {
    "server-name", "max-players", "server-port", "server-portv6", "view-distance",
    "tick-distance", "player-idle-timeout", "max-threads", "level-name", "level-seed",
    "compression-threshold", "player-position-acceptance-threshold",
    "player-movement-score-threshold", "player-movement-action-direction-threshold",
    "player-movement-distance-threshold", "player-movement-duration-threshold-in-ms",
    "server-authoritative-block-breaking-pick-range-scalar", "server-build-radius-ratio",
    "force-inbound-debug-port", "script-debugger-auto-attach-connect-address",
    "script-watchdog-hang-threshold", "script-watchdog-spike-threshold",
    "script-watchdog-slow-threshold", "script-watchdog-memory-warning",
    "script-watchdog-memory-limit", "op-permission-level",
}

BEDROCK_KNOWN_KEYS = set(BEDROCK_PROPERTY_ALLOWED_VALUES) | BEDROCK_FREEFORM_KEYS


def patch_bedrock_properties(server_id: int, changes: dict) -> dict:
    """Like patch_properties, but only accepts known Bedrock property keys
    (and, where applicable, their known allowed values) instead of anything —
    a Java-only key would otherwise be written to the file and silently
    ignored by the Bedrock server.

    Returns {"changed": [...], "rejected": [...], "restart_required": bool}.
    """
    normalized: dict[str, str] = {}
    rejected: list[str] = []
    for key, value in changes.items():
        key = str(key).strip()
        allowed = BEDROCK_PROPERTY_ALLOWED_VALUES.get(key)
        if key not in BEDROCK_KNOWN_KEYS:
            rejected.append(key)
        elif allowed and str(value).lower() not in {a.lower() for a in allowed}:
            rejected.append(key)
        else:
            normalized[key] = str(value)

    if not normalized:
        return {
            "changed": [], "rejected": rejected, "restart_required": False,
            "error": "No valid Bedrock properties in request",
        }

    result = patch_properties(server_id, normalized)
    result["rejected"] = rejected + result.get("rejected", [])
    return result


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
