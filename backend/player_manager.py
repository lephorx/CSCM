"""Player management: whitelist, ops, bans, kicks, and per-player NBT data.

Simple mutations (whitelist, ops, bans, kicks) use RCON when the server is
running; ban listing reads the JSON files directly so they work offline.

Per-player NBT operations (health / food / inventory / ender chest) read and
write the binary ``world/playerdata/<uuid>.dat`` files.  Write operations are
safe while the server is stopped.  When the server is *running* the disk file
may be stale for currently-connected players (the server flushes the in-memory
state to disk on disconnect) — a ``warning`` key is included in those responses.
Requires the ``nbtlib`` package (pip install nbtlib).
"""

import json
import re
import sqlite3
import time
from pathlib import Path

import docker_manager
import properties_manager
from db import get_db
from docker_manager import server_data_dir
from logger import get_logger

try:
    import nbtlib
    _NBT_OK = True
except ImportError:
    _NBT_OK = False

log = get_logger("player_manager")

_GAMEMODE_ALIASES = {
    "0": 0,
    "1": 1,
    "2": 2,
    "3": 3,
    "survival": 0,
    "creative": 1,
    "adventure": 2,
    "spectator": 3,
}

_DISTANCE_STATS_CM = (
    "minecraft:walk_one_cm",
    "minecraft:walk_on_water_one_cm",
    "minecraft:walk_under_water_one_cm",
    "minecraft:sprint_one_cm",
    "minecraft:crouch_one_cm",
    "minecraft:swim_one_cm",
    "minecraft:fall_one_cm",
    "minecraft:climb_one_cm",
    "minecraft:fly_one_cm",
    "minecraft:aviate_one_cm",
    "minecraft:minecart_one_cm",
    "minecraft:boat_one_cm",
    "minecraft:pig_one_cm",
    "minecraft:horse_one_cm",
    "minecraft:strider_one_cm",
)

_BLOCK_ID_HINTS = (
    "_block",
    "_planks",
    "_log",
    "_wood",
    "_stone",
    "_dirt",
    "_sand",
    "_gravel",
    "_glass",
    "_wool",
    "_terracotta",
    "_concrete",
    "_slab",
    "_stairs",
    "_wall",
    "_fence",
    "_door",
    "_trapdoor",
    "_pressure_plate",
    "_button",
    "_leaves",
    "_bricks",
)

_EFFECT_ID_RE = re.compile(r"^[a-z0-9_:.]+$")

# Real Minecraft usernames are 1-16 chars, letters/digits/underscore only.
# Guards against a corrupted/duplicated RCON "list" response (observed when
# overlapping RCON calls race — e.g. the stats poll and the players panel
# both issuing `list` at once) being parsed as if the whole raw sentence
# were a single player name.
_VALID_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{1,16}$")


def _read_json(server_id: int, filename: str) -> list:
    path = Path(server_data_dir(server_id)) / filename
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _is_running(server_id: int) -> bool:
    return docker_manager.runtime_status(server_id) not in ("not_created", "stopped")


def _is_bedrock(server_id: int) -> bool:
    return docker_manager.get_server_edition(server_id) == "bedrock"


def _whitelist_filename(server_id: int) -> str:
    # Bedrock's allow-list is a differently-named, differently-shaped file
    # (allowlist.json, keyed by name/xuid) — there is no whitelist.json.
    return "allowlist.json" if _is_bedrock(server_id) else "whitelist.json"


def get_players(server_id: int) -> dict:
    is_bedrock = _is_bedrock(server_id)
    whitelist = _read_json(server_id, _whitelist_filename(server_id))
    banned = _read_json(server_id, "banned-players.json")
    # permissions.json (Bedrock's ops-equivalent) is keyed by XUID only, no
    # name field — ops.json can't be read the same way, so use the event log.
    ops = _bedrock_known_ops(server_id) if is_bedrock else [e.get("name") for e in _read_json(server_id, "ops.json")]

    online = []
    if _is_running(server_id):
        try:
            if is_bedrock:
                # No RCON on Bedrock — reconstructed from container log
                # connect/disconnect lines instead of a `list` command.
                online = docker_manager.get_bedrock_online_players(server_id)
            else:
                output = docker_manager.send_rcon(server_id, "list")
                match = re.search(r"online:\s*(.*)$", output)
                if match and match.group(1).strip():
                    candidates = [n.strip() for n in match.group(1).split(",") if n.strip()]
                    online = [n for n in candidates if _VALID_USERNAME_RE.match(n)]
                    if len(online) != len(candidates):
                        log.warning(
                            "Discarded malformed name(s) from RCON `list` for server_id=%d: %s",
                            server_id, [n for n in candidates if n not in online],
                        )
        except Exception as exc:
            log.warning("Could not fetch online players for server_id=%d: %s", server_id, exc)

    return {
        "online": online,
        "whitelist": [e.get("name") for e in whitelist],
        "ops": ops,
        "banned": [e.get("name") for e in banned],
    }


def _require_running(server_id: int) -> tuple[bool, str]:
    if not _is_running(server_id):
        return False, "Server must be running to perform this action"
    return True, ""


def _write_json(server_id: int, filename: str, data: list) -> None:
    path = Path(server_data_dir(server_id)) / filename
    path.write_text(json.dumps(data, indent=2))


# ── Bedrock event log (schema: bedrock_player_events) ──────────────────────────
# Bedrock has no per-player stats files to read back, so whitelist/op changes
# made through this API are logged here as an audit trail, and "current
# status" is derived by taking the latest event per (server, username, kind).

def _log_bedrock_event(server_id: int, username: str, event_type: str, xuid: str | None = None) -> None:
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO bedrock_player_events (server_id, username, xuid, event_type)"
                " VALUES (?, ?, ?, ?)",
                (server_id, username, xuid, event_type),
            )
    except sqlite3.Error as exc:
        log.warning("Could not log bedrock event server_id=%d user=%s event=%s: %s",
                    server_id, username, event_type, exc)


def _bedrock_event_history(server_id: int, username: str, limit: int = 20) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT event_type, xuid, created_at FROM bedrock_player_events"
            " WHERE server_id = ? AND username = ? COLLATE NOCASE"
            " ORDER BY id DESC LIMIT ?",
            (server_id, username, limit),
        ).fetchall()
    return [{"event": r["event_type"], "xuid": r["xuid"], "at": r["created_at"]} for r in rows]


def _bedrock_known_ops(server_id: int) -> list[str]:
    """Usernames whose latest op_add/op_remove event (made through this API)
    was op_add. permissions.json has no name field to read this back
    directly, so the event log is the only source for a name-keyed op list.
    """
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT username FROM bedrock_player_events e1
            WHERE server_id = ? AND event_type IN ('op_add', 'op_remove')
              AND id = (
                  SELECT MAX(id) FROM bedrock_player_events e2
                  WHERE e2.server_id = e1.server_id
                    AND e2.username = e1.username COLLATE NOCASE
                    AND e2.event_type IN ('op_add', 'op_remove')
              )
              AND event_type = 'op_add'
            """,
            (server_id,),
        ).fetchall()
    return [r["username"] for r in rows]


def _resolve_bedrock_xuid(server_id: int, username: str) -> str | None:
    """Best-effort XUID lookup: live connect-log scan first (most current),
    then allowlist.json, then our own event log. Bedrock's permissions.json
    is keyed by XUID only, so this is required before op/deop or an operator
    status check can work at all.
    """
    xuid = docker_manager.get_bedrock_player_xuid(server_id, username)
    if xuid:
        return xuid
    for entry in _read_json(server_id, "allowlist.json"):
        if entry.get("name", "").lower() == username.lower() and entry.get("xuid"):
            return str(entry["xuid"])
    with get_db() as conn:
        row = conn.execute(
            "SELECT xuid FROM bedrock_player_events"
            " WHERE server_id = ? AND username = ? COLLATE NOCASE AND xuid IS NOT NULL"
            " ORDER BY id DESC LIMIT 1",
            (server_id, username),
        ).fetchone()
    return row["xuid"] if row else None


def _ensure_bedrock_allowlist_enabled(server_id: int) -> None:
    """Bedrock ignores allowlist.json entirely unless allow-list=true. Persist
    it to server.properties (survives container recreation) and, best-effort,
    flip enforcement on immediately if the server is currently running.
    """
    try:
        properties_manager.patch_properties(server_id, {"allow-list": "true"})
    except Exception as exc:
        log.warning("Could not set allow-list=true for server_id=%d: %s", server_id, exc)
    if _is_running(server_id):
        try:
            docker_manager.send_rcon(server_id, "allowlist on")
        except Exception as exc:
            log.warning("allowlist on failed for server_id=%d: %s", server_id, exc)


def whitelist_add(server_id: int, username: str) -> dict:
    if _is_bedrock(server_id):
        _ensure_bedrock_allowlist_enabled(server_id)
        if _is_running(server_id):
            # Bedrock's real console command — confirmed against Microsoft's
            # docs (in-game "/allowlist add", console form drops the slash
            # like op/deop do). send-command has no output, so verify by
            # reading allowlist.json back afterward.
            docker_manager.send_rcon(server_id, f'allowlist add "{username}"')
            time.sleep(0.3)
            entries = _read_json(server_id, "allowlist.json")
            if not any(e.get("name", "").lower() == username.lower() for e in entries):
                return {"success": False, "message": f"Could not confirm {username} was added to the allowlist"}
        else:
            # No running console to talk to — edit the file directly. Also
            # works this way, so whitelisting still functions while stopped.
            entries = _read_json(server_id, "allowlist.json")
            if not any(e.get("name", "").lower() == username.lower() for e in entries):
                entries.append({"name": username, "ignoresPlayerLimit": False})
                try:
                    _write_json(server_id, "allowlist.json", entries)
                except OSError as exc:
                    return {"success": False, "message": f"Could not write allowlist.json: {exc}"}

        _log_bedrock_event(server_id, username, "whitelist_add")
        return {"success": True, "message": f"{username} added to allowlist"}

    ok, msg = _require_running(server_id)
    if not ok:
        return {"success": False, "message": msg}
    output = docker_manager.send_rcon(server_id, f"whitelist add {username}")
    return {"success": True, "message": output}


def whitelist_remove(server_id: int, username: str) -> dict:
    if _is_bedrock(server_id):
        if _is_running(server_id):
            docker_manager.send_rcon(server_id, f'allowlist remove "{username}"')
            time.sleep(0.3)
            entries = _read_json(server_id, "allowlist.json")
            if any(e.get("name", "").lower() == username.lower() for e in entries):
                return {"success": False, "message": f"Could not confirm {username} was removed from the allowlist"}
        else:
            entries = _read_json(server_id, "allowlist.json")
            before = len(entries)
            entries = [e for e in entries if e.get("name", "").lower() != username.lower()]
            if len(entries) == before:
                return {"success": True, "message": f"{username} was not on the allowlist"}
            try:
                _write_json(server_id, "allowlist.json", entries)
            except OSError as exc:
                return {"success": False, "message": f"Could not write allowlist.json: {exc}"}

        _log_bedrock_event(server_id, username, "whitelist_remove")
        return {"success": True, "message": f"{username} removed from allowlist"}

    ok, msg = _require_running(server_id)
    if not ok:
        return {"success": False, "message": msg}
    output = docker_manager.send_rcon(server_id, f"whitelist remove {username}")
    return {"success": True, "message": output}


def op_add(server_id: int, username: str) -> dict:
    if _is_bedrock(server_id):
        # permissions.json is keyed by XUID only (no name field) — BDS can
        # only resolve "op <name>" for a player it already knows, so we need
        # their XUID up front both to issue the command sensibly and to
        # verify it afterward (send-command gives no output to check).
        xuid = _resolve_bedrock_xuid(server_id, username)
        if not xuid:
            return {
                "success": False,
                "message": f"'{username}' must have connected to the server at least once "
                           "before they can be made an operator (Bedrock resolves op by XUID, "
                           "which is only known once a player has joined)",
            }
        ok, msg = _require_running(server_id)
        if not ok:
            return {"success": False, "message": msg}
        docker_manager.send_rcon(server_id, f'op "{username}"')
        time.sleep(0.3)
        perms = _read_json(server_id, "permissions.json")
        if not any(p.get("xuid") == xuid and p.get("permission") == "operator" for p in perms):
            return {"success": False, "message": f"Could not confirm operator status for {username}"}
        _log_bedrock_event(server_id, username, "op_add", xuid=xuid)
        return {"success": True, "message": f"{username} is now an operator"}

    ok, msg = _require_running(server_id)
    if not ok:
        return {"success": False, "message": msg}
    output = docker_manager.send_rcon(server_id, f"op {username}")
    return {"success": True, "message": output}


def op_remove(server_id: int, username: str) -> dict:
    if _is_bedrock(server_id):
        xuid = _resolve_bedrock_xuid(server_id, username)
        ok, msg = _require_running(server_id)
        if not ok:
            return {"success": False, "message": msg}
        docker_manager.send_rcon(server_id, f'deop "{username}"')
        if xuid:
            time.sleep(0.3)
            perms = _read_json(server_id, "permissions.json")
            if any(p.get("xuid") == xuid and p.get("permission") == "operator" for p in perms):
                return {"success": False, "message": f"Could not confirm {username} was deopped"}
        _log_bedrock_event(server_id, username, "op_remove", xuid=xuid)
        return {"success": True, "message": f"{username} is no longer an operator"}

    ok, msg = _require_running(server_id)
    if not ok:
        return {"success": False, "message": msg}
    output = docker_manager.send_rcon(server_id, f"deop {username}")
    return {"success": True, "message": output}


def ban_add(server_id: int, username: str, reason: str | None = None) -> dict:
    if _is_bedrock(server_id):
        # Bedrock's dedicated server has no ban/pardon console command and no
        # banned-players.json equivalent — silently "succeeding" here would
        # just lie about having banned anyone.
        return {"success": False, "message": "Bans are not supported on Bedrock servers"}
    ok, msg = _require_running(server_id)
    if not ok:
        return {"success": False, "message": msg}
    command = f"ban {username} {reason}" if reason else f"ban {username}"
    output = docker_manager.send_rcon(server_id, command)
    return {"success": True, "message": output}


def ban_remove(server_id: int, username: str) -> dict:
    if _is_bedrock(server_id):
        return {"success": False, "message": "Bans are not supported on Bedrock servers"}
    if _is_running(server_id):
        try:
            output = docker_manager.send_rcon(server_id, f"pardon {username}")
            return {"success": True, "message": output}
        except Exception as exc:
            log.warning("RCON pardon failed for server_id=%d, falling back to file edit: %s", server_id, exc)

    # Server stopped (or RCON failed) — edit banned-players.json directly.
    path = Path(server_data_dir(server_id)) / "banned-players.json"
    if not path.exists():
        return {"success": True, "message": f"{username} was not banned"}
    bans = _read_json(server_id, "banned-players.json")
    before = len(bans)
    bans = [b for b in bans if b.get("name", "").lower() != username.lower()]
    if len(bans) == before:
        return {"success": True, "message": f"{username} was not banned"}
    try:
        path.write_text(json.dumps(bans, indent=2))
    except OSError as exc:
        return {"success": False, "message": f"Could not write banned-players.json: {exc}"}
    return {"success": True, "message": f"Unbanned {username}"}


def kick(server_id: int, username: str, reason: str | None = None) -> dict:
    ok, msg = _require_running(server_id)
    if not ok:
        return {"success": False, "message": msg}
    command = f"kick {username} {reason}" if reason else f"kick {username}"
    output = docker_manager.send_rcon(server_id, command)
    return {"success": True, "message": output}


# ── Ban details ───────────────────────────────────────────────────────────────

def get_bans_detailed(server_id: int) -> list[dict]:
    """Return full banned-players.json entries (uuid, name, created, expires, reason, source)."""
    return _read_json(server_id, "banned-players.json")


# ── Player history ────────────────────────────────────────────────────────────

def get_player_history(server_id: int) -> list[dict]:
    """Return all players who have ever joined, sourced from usercache.json."""
    return [
        {"name": e.get("name"), "uuid": e.get("uuid"), "last_seen": e.get("expiresOn")}
        for e in _read_json(server_id, "usercache.json")
    ]


# ── NBT helpers ───────────────────────────────────────────────────────────────

def _player_dat(server_id: int, uuid: str) -> Path:
    return Path(server_data_dir(server_id)) / "world" / "playerdata" / f"{uuid}.dat"


def _player_dat_old(server_id: int, uuid: str) -> Path:
    return Path(server_data_dir(server_id)) / "world" / "playerdata" / f"{uuid}.dat_old"


def _lookup_uuid(server_id: int, username: str) -> str | None:
    for entry in _read_json(server_id, "usercache.json"):
        if entry.get("name", "").lower() == username.lower():
            return entry.get("uuid")
    return None


def _nbt_open(server_id: int, username: str):
    """Load player NBT.  Returns ``(nbt_file, root_compound, uuid, error_str)``."""
    if not _NBT_OK:
        return None, None, None, "nbtlib is not installed — run: pip install nbtlib"
    uuid = _lookup_uuid(server_id, username)
    if uuid is None:
        return None, None, None, (
            f"Player '{username}' not found in usercache.json — "
            "they must have joined the server at least once"
        )
    dat = _player_dat(server_id, uuid)
    if not dat.exists():
        dat_old = _player_dat_old(server_id, uuid)
        if dat_old.exists():
            dat = dat_old
        else:
            return None, None, uuid, f"Player data file not found (UUID: {uuid})"
    try:
        nbt_file = nbtlib.load(str(dat))
        # nbtlib 2.x: File IS the root compound — no ["" ] indirection needed
        return nbt_file, nbt_file, uuid, None
    except Exception as exc:
        return None, None, None, f"Failed to parse NBT: {exc}"


def _nbt_save(nbt_file, server_id: int, uuid: str) -> str | None:
    """Write NBT back to disk.  Returns an error string or ``None`` on success."""
    try:
        nbt_file.save(str(_player_dat(server_id, uuid)))
        return None
    except Exception as exc:
        return str(exc)


def _item_to_dict(item) -> dict:
    """Convert an NBT item compound to a plain serialisable dict.

    Handles both the pre-1.20.5 format (``Count: byte``) and the 1.20.5+
    format (``count: int``) transparently.
    """
    d = {
        "slot":  int(item.get("Slot", 0)),
        "id":    str(item.get("id", "")),
        "count": int(item.get("count", item.get("Count", 1))),
    }
    if "components" in item:
        try:
            d["components"] = str(item["components"])
        except Exception:
            pass
    elif "tag" in item:
        try:
            d["nbt"] = str(item["tag"])
        except Exception:
            pass
    return d


def _make_item(slot: int, item_id: str, count: int) -> "nbtlib.Compound":
    """Build a new item compound in 1.20.5+ format."""
    return nbtlib.Compound({
        "Slot":  nbtlib.Byte(slot),
        "id":    nbtlib.String(item_id),
        "count": nbtlib.Int(count),
    })


def _running_warning() -> str:
    return (
        "Server is running — if the player is currently connected their "
        "in-memory state will overwrite this file when they disconnect. "
        "Changes are safe for offline players."
    )


def _rcon_failed(output: str) -> bool:
    text = (output or "").strip().lower()
    if not text:
        return False
    failure_markers = (
        "no player was found",
        "unknown or incomplete command",
        "syntax error",
        "unable to modify player data",
        "expected whitespace",
    )
    return any(marker in text for marker in failure_markers)


def _run_live_player_commands(server_id: int, commands: list[str]) -> dict:
    outputs: list[str] = []
    for command in commands:
        output = docker_manager.send_rcon(server_id, command)
        if _rcon_failed(output):
            return {"success": False, "message": output or "Command failed"}
        if output:
            outputs.append(output)
    return {"success": True, "message": "\n".join(outputs)}


def _parse_gamemode(value) -> int | None:
    if value is None:
        return None
    return _GAMEMODE_ALIASES.get(str(value).strip().lower())


def _gamemode_name(mode: int) -> str:
    return {
        0: "survival",
        1: "creative",
        2: "adventure",
        3: "spectator",
    }.get(mode, str(mode))


def _parse_pos_from_rcon(output: str) -> tuple[float, float, float] | None:
    match = re.search(r"\[\s*(-?\d+(?:\.\d+)?)d?,\s*(-?\d+(?:\.\d+)?)d?,\s*(-?\d+(?:\.\d+)?)d?\s*\]", output)
    if not match:
        return None
    return float(match.group(1)), float(match.group(2)), float(match.group(3))


def _normalize_effect_id(effect_id: str) -> str | None:
    effect_id = str(effect_id or "").strip().lower()
    if not effect_id:
        return None
    if ":" not in effect_id:
        effect_id = f"minecraft:{effect_id}"
    if not _EFFECT_ID_RE.match(effect_id):
        return None
    return effect_id


def _looks_like_block_stat(stat_key: str) -> bool:
    if not stat_key.startswith("minecraft:"):
        return False
    name = stat_key.split(":", 1)[1]
    return any(name.endswith(suffix) for suffix in _BLOCK_ID_HINTS)


# ── Player NBT data (read) ────────────────────────────────────────────────────

def get_player_data(server_id: int, username: str) -> dict:
    """Return health, food, XP, game mode, inventory and ender chest from the .dat file."""
    nbt_file, root, uuid, err = _nbt_open(server_id, username)
    if err:
        return {"success": False, "message": err}

    result = {
        "success":         True,
        "uuid":            uuid,
        "username":        username,
        "health":          float(root.get("Health",              nbtlib.Float(20.0))),
        "food_level":      int(root.get("foodLevel",            nbtlib.Int(20))),
        "food_saturation": float(root.get("foodSaturationLevel", nbtlib.Float(5.0))),
        "xp_level":        int(root.get("XpLevel",              nbtlib.Int(0))),
        "game_mode":       int(root.get("playerGameType",       nbtlib.Int(0))),
        "inventory":       [_item_to_dict(i) for i in root.get("Inventory",  nbtlib.List())],
        "enderchest":      [_item_to_dict(i) for i in root.get("EnderItems", nbtlib.List())],
    }
    if _is_running(server_id):
        result["warning"] = _running_warning()
    return result


# ── Player actions ────────────────────────────────────────────────────────────

def set_player_gamemode(server_id: int, username: str, game_mode) -> dict:
    mode = _parse_gamemode(game_mode)
    if mode is None:
        return {
            "success": False,
            "message": "Invalid game_mode. Use 0-3 or survival|creative|adventure|spectator",
        }

    if _is_running(server_id):
        output = docker_manager.send_rcon(server_id, f"gamemode {_gamemode_name(mode)} {username}")
        return {"success": True, "message": output, "game_mode": mode}

    nbt_file, root, uuid, err = _nbt_open(server_id, username)
    if err:
        return {"success": False, "message": err}

    root["playerGameType"] = nbtlib.Int(mode)
    save_err = _nbt_save(nbt_file, server_id, uuid)
    if save_err:
        return {"success": False, "message": save_err}
    return {
        "success": True,
        "message": f"Set game mode for {username} to {_gamemode_name(mode)}",
        "game_mode": mode,
    }


def _broadcast_red_message(server_id: int, message: str) -> None:
    """Best-effort broadcast of `message` in red to all players via tellraw.

    Bedrock and Java use different JSON schemas for tellraw: Java has a flat
    {"text": ..., "color": "red"} format, but Bedrock has no top-level
    "color" key at all — it needs the {"rawtext": [{"text": ...}]} wrapper
    with a section-sign (§c) format code embedded directly in the text.
    """
    if _is_bedrock(server_id):
        payload = json.dumps({"rawtext": [{"text": f"§c{message}"}]})
    else:
        payload = json.dumps({"text": message, "color": "red"})
    try:
        # raw=True: the JSON payload's embedded quotes would otherwise be
        # mangled by rcon-cli's shlex-based command splitting.
        docker_manager.send_rcon(server_id, f"tellraw @a {payload}", raw=True)
    except Exception as exc:
        log.warning("Could not broadcast message for server_id=%d: %s", server_id, exc)


def kill_player(server_id: int, username: str, message: str | None = None) -> dict:
    ok, msg = _require_running(server_id)
    if not ok:
        return {"success": False, "message": msg}
    output = docker_manager.send_rcon(server_id, f"kill {username}")
    if message:
        _broadcast_red_message(server_id, message)
    return {"success": True, "message": output}


def heal_player(server_id: int, username: str) -> dict:
    if _is_running(server_id):
        return _run_live_player_commands(server_id, [
            f"effect give {username} instant_health 1 255 true",
            f"effect give {username} saturation 1 255 true",
        ])

    nbt_file, root, uuid, err = _nbt_open(server_id, username)
    if err:
        return {"success": False, "message": err}
    root["Health"] = nbtlib.Float(20.0)
    root["foodLevel"] = nbtlib.Int(20)
    root["foodSaturationLevel"] = nbtlib.Float(5.0)
    save_err = _nbt_save(nbt_file, server_id, uuid)
    if save_err:
        return {"success": False, "message": save_err}
    return {"success": True, "message": f"Healed {username}"}


def starve_player(server_id: int, username: str) -> dict:
    if _is_running(server_id):
        return _run_live_player_commands(server_id, [
            f"effect clear {username} saturation",
            f"effect give {username} hunger 2 255 true",
        ])

    nbt_file, root, uuid, err = _nbt_open(server_id, username)
    if err:
        return {"success": False, "message": err}
    root["foodLevel"] = nbtlib.Int(0)
    root["foodSaturationLevel"] = nbtlib.Float(0.0)
    save_err = _nbt_save(nbt_file, server_id, uuid)
    if save_err:
        return {"success": False, "message": save_err}
    return {"success": True, "message": f"Starved {username}"}


def feed_player(server_id: int, username: str) -> dict:
    if _is_running(server_id):
        return _run_live_player_commands(server_id, [
            f"effect clear {username} hunger",
            f"effect give {username} saturation 1 255 true",
        ])

    nbt_file, root, uuid, err = _nbt_open(server_id, username)
    if err:
        return {"success": False, "message": err}
    root["foodLevel"] = nbtlib.Int(20)
    root["foodSaturationLevel"] = nbtlib.Float(5.0)
    save_err = _nbt_save(nbt_file, server_id, uuid)
    if save_err:
        return {"success": False, "message": save_err}
    return {"success": True, "message": f"Fed {username}"}


def add_player_effect(
    server_id: int,
    username: str,
    effect_id: str,
    seconds: int = 30,
    amplifier: int = 0,
    hide_particles: bool = True,
) -> dict:
    ok, msg = _require_running(server_id)
    if not ok:
        return {"success": False, "message": msg}

    effect = _normalize_effect_id(effect_id)
    if effect is None:
        return {"success": False, "message": "Invalid effect ID"}
    if seconds < 1:
        return {"success": False, "message": "seconds must be >= 1"}
    if amplifier < 0:
        return {"success": False, "message": "amplifier must be >= 0"}

    output = docker_manager.send_rcon(
        server_id,
        f"effect give {username} {effect} {seconds} {amplifier} {'true' if hide_particles else 'false'}",
    )
    if _rcon_failed(output):
        return {"success": False, "message": output or "Command failed"}
    return {
        "success": True,
        "message": output,
        "effect": effect,
        "seconds": seconds,
        "amplifier": amplifier,
        "hide_particles": hide_particles,
    }


def clear_player_effect(server_id: int, username: str, effect_id: str) -> dict:
    ok, msg = _require_running(server_id)
    if not ok:
        return {"success": False, "message": msg}

    effect = _normalize_effect_id(effect_id)
    if effect is None:
        return {"success": False, "message": "Invalid effect ID"}

    output = docker_manager.send_rcon(server_id, f"effect clear {username} {effect}")
    if _rcon_failed(output):
        return {"success": False, "message": output or "Command failed"}
    return {"success": True, "message": output, "effect": effect}


def clear_all_player_effects(server_id: int, username: str) -> dict:
    ok, msg = _require_running(server_id)
    if not ok:
        return {"success": False, "message": msg}

    output = docker_manager.send_rcon(server_id, f"effect clear {username}")
    if _rcon_failed(output):
        return {"success": False, "message": output or "Command failed"}
    return {"success": True, "message": output}


def get_player_position(server_id: int, username: str) -> dict:
    if _is_running(server_id):
        try:
            output = docker_manager.send_rcon(server_id, f"data get entity {username} Pos")
            pos = _parse_pos_from_rcon(output)
            if pos is not None:
                x, y, z = pos
                return {
                    "success": True,
                    "username": username,
                    "position": {"x": x, "y": y, "z": z},
                    "source": "rcon",
                }
        except Exception as exc:
            log.warning("Could not fetch live position for server_id=%d user=%s: %s", server_id, username, exc)

    nbt_file, root, uuid, err = _nbt_open(server_id, username)
    if err:
        return {"success": False, "message": err}

    pos = root.get("Pos", nbtlib.List[nbtlib.Double]([0.0, 0.0, 0.0]))
    x = float(pos[0]) if len(pos) > 0 else 0.0
    y = float(pos[1]) if len(pos) > 1 else 0.0
    z = float(pos[2]) if len(pos) > 2 else 0.0
    result = {
        "success": True,
        "username": username,
        "position": {"x": x, "y": y, "z": z},
        "source": "playerdata",
    }
    if _is_running(server_id):
        result["warning"] = _running_warning()
    return result


def teleport_player(server_id: int, username: str, x: float, y: float, z: float) -> dict:
    if _is_running(server_id):
        output = docker_manager.send_rcon(server_id, f"tp {username} {x} {y} {z}")
        return {
            "success": True,
            "message": output,
            "position": {"x": x, "y": y, "z": z},
        }

    nbt_file, root, uuid, err = _nbt_open(server_id, username)
    if err:
        return {"success": False, "message": err}
    root["Pos"] = nbtlib.List[nbtlib.Double]([x, y, z])
    save_err = _nbt_save(nbt_file, server_id, uuid)
    if save_err:
        return {"success": False, "message": save_err}
    return {
        "success": True,
        "message": f"Set saved position for {username}",
        "position": {"x": x, "y": y, "z": z},
    }


# ── Statistics ────────────────────────────────────────────────────────────────

def get_player_statistics(server_id: int, username: str) -> dict:
    if _is_bedrock(server_id):
        # Bedrock has no equivalent of Java's world/stats/<uuid>.json — it
        # stores the whole world (including player data) in LevelDB, a
        # different storage engine with an undocumented internal schema, so
        # gameplay stats (blocks mined, playtime, etc.) aren't available.
        # Whitelist/operator status is tracked separately (see the events
        # table), so report that instead of a flat "not supported".
        whitelisted = any(
            e.get("name", "").lower() == username.lower()
            for e in _read_json(server_id, "allowlist.json")
        )
        xuid = _resolve_bedrock_xuid(server_id, username)
        operator = None
        if xuid:
            perms = _read_json(server_id, "permissions.json")
            operator = any(p.get("xuid") == xuid and p.get("permission") == "operator" for p in perms)
        return {
            "success": True,
            "username": username,
            "xuid": xuid,
            "statistics": {
                "whitelisted": whitelisted,
                "operator": operator,
            },
            "history": _bedrock_event_history(server_id, username),
            "note": "Gameplay statistics (blocks mined, playtime, kills, etc.) aren't available "
                    "for Bedrock — it stores player data in LevelDB, not per-player stats files. "
                    "'operator' is null if this player has never connected (Bedrock resolves "
                    "operator status by XUID, which is only known once a player has joined).",
        }

    uuid = _lookup_uuid(server_id, username)
    if not uuid:
        return {
            "success": False,
            "message": f"Player '{username}' not found in usercache.json — they must have joined at least once",
        }

    stats_path = Path(server_data_dir(server_id)) / "world" / "stats" / f"{uuid}.json"
    if not stats_path.exists():
        return {"success": False, "message": f"Statistics file not found (UUID: {uuid})"}

    try:
        payload = json.loads(stats_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return {"success": False, "message": f"Failed to read statistics: {exc}"}

    stats = payload.get("stats", {}) if isinstance(payload, dict) else {}
    custom = stats.get("minecraft:custom", {}) if isinstance(stats.get("minecraft:custom", {}), dict) else {}
    mined = stats.get("minecraft:mined", {}) if isinstance(stats.get("minecraft:mined", {}), dict) else {}
    used = stats.get("minecraft:used", {}) if isinstance(stats.get("minecraft:used", {}), dict) else {}
    killed = stats.get("minecraft:killed", {}) if isinstance(stats.get("minecraft:killed", {}), dict) else {}

    playtime_ticks = int(custom.get("minecraft:play_time", 0))
    playtime_seconds = int(playtime_ticks / 20)
    deaths = int(custom.get("minecraft:deaths", 0))
    player_kills = int(custom.get("minecraft:player_kills", 0))
    kd = round(player_kills / deaths, 3) if deaths > 0 else float(player_kills)

    distance_cm = sum(int(custom.get(key, 0)) for key in _DISTANCE_STATS_CM)
    distance_blocks = round(distance_cm / 100.0, 2)

    blocks_added = sum(int(value) for key, value in used.items() if _looks_like_block_stat(key))

    result = {
        "success": True,
        "username": username,
        "uuid": uuid,
        "statistics": {
            "playtime_ticks": playtime_ticks,
            "playtime_seconds": playtime_seconds,
            "playtime_hours": round(playtime_seconds / 3600.0, 2),
            "deaths": deaths,
            "player_kills": player_kills,
            "kd": kd,
            "distance_traveled_blocks": distance_blocks,
            "blocks_removed": int(sum(mined.values())),
            "blocks_added": int(blocks_added),
            "items_used": int(sum(used.values())),
            "entities_killed": int(sum(killed.values())),
        },
    }
    return result


# ── Selective player data reset/deletion ─────────────────────────────────────

def delete_player_data(server_id: int, username: str, targets: list[str]) -> dict:
    allowed = {"xp", "inventory", "enderchest", "playerdata", "statistics", "advancements", "everything"}
    normalized = {str(t).strip().lower() for t in targets if str(t).strip()}
    if not normalized:
        return {"success": False, "message": "At least one target is required"}
    invalid = sorted(normalized - allowed)
    if invalid:
        return {"success": False, "message": f"Invalid targets: {', '.join(invalid)}"}
    if "everything" in normalized:
        normalized = {"xp", "inventory", "enderchest", "playerdata", "statistics", "advancements"}

    uuid = _lookup_uuid(server_id, username)
    if not uuid:
        return {
            "success": False,
            "message": f"Player '{username}' not found in usercache.json — they must have joined at least once",
        }

    deleted: list[str] = []
    not_found: list[str] = []

    dat_path = _player_dat(server_id, uuid)
    dat_old_path = _player_dat_old(server_id, uuid)
    stats_path = Path(server_data_dir(server_id)) / "world" / "stats" / f"{uuid}.json"
    advancements_path = Path(server_data_dir(server_id)) / "world" / "advancements" / f"{uuid}.json"

    needs_nbt_edit = bool(normalized & {"xp", "inventory", "enderchest"})
    if needs_nbt_edit:
        nbt_file, root, _, err = _nbt_open(server_id, username)
        if err:
            return {"success": False, "message": err}
        if "xp" in normalized:
            root["XpLevel"] = nbtlib.Int(0)
            root["XpTotal"] = nbtlib.Int(0)
            root["XpP"] = nbtlib.Float(0.0)
            deleted.append("xp")
        if "inventory" in normalized:
            root["Inventory"] = nbtlib.List[nbtlib.Compound]()
            deleted.append("inventory")
        if "enderchest" in normalized:
            root["EnderItems"] = nbtlib.List[nbtlib.Compound]()
            deleted.append("enderchest")
        if "playerdata" not in normalized:
            save_err = _nbt_save(nbt_file, server_id, uuid)
            if save_err:
                return {"success": False, "message": save_err}

    if "playerdata" in normalized:
        if dat_path.exists() or dat_old_path.exists():
            try:
                dat_path.unlink(missing_ok=True)
                dat_old_path.unlink(missing_ok=True)
                deleted.append("playerdata")
            except OSError as exc:
                return {"success": False, "message": f"Could not delete playerdata: {exc}"}
        else:
            not_found.append("playerdata")

    if "statistics" in normalized:
        if stats_path.exists():
            try:
                stats_path.unlink()
                deleted.append("statistics")
            except OSError as exc:
                return {"success": False, "message": f"Could not delete statistics: {exc}"}
        else:
            not_found.append("statistics")

    if "advancements" in normalized:
        if advancements_path.exists():
            try:
                advancements_path.unlink()
                deleted.append("advancements")
            except OSError as exc:
                return {"success": False, "message": f"Could not delete advancements: {exc}"}
        else:
            not_found.append("advancements")

    result: dict = {
        "success": True,
        "message": f"Applied player data reset for {username}",
        "deleted": sorted(set(deleted)),
        "not_found": sorted(set(not_found)),
    }
    if _is_running(server_id):
        result["warning"] = _running_warning()
    return result


# ── Inventory mutations ───────────────────────────────────────────────────────

def clear_inventory(server_id: int, username: str) -> dict:
    """Clear all items from a player's inventory."""
    if _is_running(server_id):
        try:
            output = docker_manager.send_rcon(server_id, f"clear {username}")
            return {"success": True, "message": output}
        except Exception as exc:
            log.warning("RCON clear failed for server_id=%d, falling back to NBT: %s", server_id, exc)

    nbt_file, root, uuid, err = _nbt_open(server_id, username)
    if err:
        return {"success": False, "message": err}
    root["Inventory"] = nbtlib.List[nbtlib.Compound]()
    save_err = _nbt_save(nbt_file, server_id, uuid)
    if save_err:
        return {"success": False, "message": save_err}
    return {"success": True, "message": f"Inventory cleared for {username}"}


def remove_inventory_item(server_id: int, username: str, slot: int) -> dict:
    """Remove the item at the given inventory slot (0-35, 100-103, -106)."""
    nbt_file, root, uuid, err = _nbt_open(server_id, username)
    if err:
        return {"success": False, "message": err}

    items = list(root.get("Inventory", nbtlib.List()))
    before = len(items)
    items = [i for i in items if int(i.get("Slot", -999)) != slot]
    if len(items) == before:
        return {"success": False, "message": f"No item found in inventory slot {slot}"}

    root["Inventory"] = nbtlib.List[nbtlib.Compound](items)
    save_err = _nbt_save(nbt_file, server_id, uuid)
    if save_err:
        return {"success": False, "message": save_err}
    result: dict = {"success": True, "message": f"Removed item from inventory slot {slot}"}
    if _is_running(server_id):
        result["warning"] = _running_warning()
    return result


def give_inventory_item(
    server_id: int,
    username: str,
    item_id: str,
    count: int = 1,
    slot: int | None = None,
) -> dict:
    """Add an item to a player's inventory.

    Uses RCON ``/give`` when the server is running (item appears in the player's
    inventory immediately without a reconnect).  Falls back to NBT editing when
    the server is stopped.
    """
    if not re.match(r"^[a-z0-9_:./-]+$", item_id):
        return {"success": False, "message": f"Invalid item ID: {item_id!r}"}
    if count < 1:
        return {"success": False, "message": "count must be ≥ 1"}

    if _is_running(server_id):
        try:
            output = docker_manager.send_rcon(server_id, f"give {username} {item_id} {count}")
            return {"success": True, "message": output}
        except Exception as exc:
            log.warning("RCON give failed for server_id=%d, falling back to NBT: %s", server_id, exc)

    nbt_file, root, uuid, err = _nbt_open(server_id, username)
    if err:
        return {"success": False, "message": err}

    items = list(root.get("Inventory", nbtlib.List()))
    used_slots = {int(i.get("Slot", -999)) for i in items}

    if slot is None:
        for candidate in range(36):
            if candidate not in used_slots:
                slot = candidate
                break
        else:
            return {"success": False, "message": "Inventory is full (slots 0-35 are all occupied)"}
    else:
        items = [i for i in items if int(i.get("Slot", -999)) != slot]

    items.append(_make_item(slot, item_id, count))
    root["Inventory"] = nbtlib.List[nbtlib.Compound](items)
    save_err = _nbt_save(nbt_file, server_id, uuid)
    if save_err:
        return {"success": False, "message": save_err}
    return {"success": True, "message": f"Added {count}× {item_id} to inventory slot {slot}"}


# ── Ender chest mutations ─────────────────────────────────────────────────────

def clear_enderchest(server_id: int, username: str) -> dict:
    """Clear all items from a player's ender chest."""
    nbt_file, root, uuid, err = _nbt_open(server_id, username)
    if err:
        return {"success": False, "message": err}
    root["EnderItems"] = nbtlib.List[nbtlib.Compound]()
    save_err = _nbt_save(nbt_file, server_id, uuid)
    if save_err:
        return {"success": False, "message": save_err}
    result: dict = {"success": True, "message": f"Ender chest cleared for {username}"}
    if _is_running(server_id):
        result["warning"] = _running_warning()
    return result


def remove_enderchest_item(server_id: int, username: str, slot: int) -> dict:
    """Remove the item at the given ender chest slot (0-26)."""
    nbt_file, root, uuid, err = _nbt_open(server_id, username)
    if err:
        return {"success": False, "message": err}

    items = list(root.get("EnderItems", nbtlib.List()))
    before = len(items)
    items = [i for i in items if int(i.get("Slot", -999)) != slot]
    if len(items) == before:
        return {"success": False, "message": f"No item found in ender chest slot {slot}"}

    root["EnderItems"] = nbtlib.List[nbtlib.Compound](items)
    save_err = _nbt_save(nbt_file, server_id, uuid)
    if save_err:
        return {"success": False, "message": save_err}
    result: dict = {"success": True, "message": f"Removed item from ender chest slot {slot}"}
    if _is_running(server_id):
        result["warning"] = _running_warning()
    return result


def give_enderchest_item(
    server_id: int,
    username: str,
    item_id: str,
    count: int = 1,
    slot: int | None = None,
) -> dict:
    """Add an item to a player's ender chest via NBT file editing.

    The ender chest has 27 slots (0-26).  Always operates on the disk file;
    add a ``warning`` if the server is running.
    """
    if not re.match(r"^[a-z0-9_:./-]+$", item_id):
        return {"success": False, "message": f"Invalid item ID: {item_id!r}"}
    if count < 1:
        return {"success": False, "message": "count must be ≥ 1"}
    if slot is not None and not (0 <= slot <= 26):
        return {"success": False, "message": "Ender chest slots are 0-26"}

    nbt_file, root, uuid, err = _nbt_open(server_id, username)
    if err:
        return {"success": False, "message": err}

    items = list(root.get("EnderItems", nbtlib.List()))
    used_slots = {int(i.get("Slot", -999)) for i in items}

    if slot is None:
        for candidate in range(27):
            if candidate not in used_slots:
                slot = candidate
                break
        else:
            return {"success": False, "message": "Ender chest is full (all 27 slots occupied)"}
    else:
        items = [i for i in items if int(i.get("Slot", -999)) != slot]

    items.append(_make_item(slot, item_id, count))
    root["EnderItems"] = nbtlib.List[nbtlib.Compound](items)
    save_err = _nbt_save(nbt_file, server_id, uuid)
    if save_err:
        return {"success": False, "message": save_err}
    result: dict = {"success": True, "message": f"Added {count}× {item_id} to ender chest slot {slot}"}
    if _is_running(server_id):
        result["warning"] = _running_warning()
    return result
