"""Connection settings (Playit, Cloudflare) edited from the dashboard.

Values live in the installation's ``.env``, which docker-compose.yml mounts into
the API container at ``CSCM_ENV_FILE``. Saving writes them back into that file
(same ``KEY='value'`` format as the installer, other lines untouched) and applies
them to this process right away, so no restart is needed. Hand edits to ``.env``
are picked up on the next API start (``load_env_file`` runs at import time).

Also keeps the first-run setup progress, so the dashboard's setup wizard can
resume where the user left off, and runs the optional Playit agent container.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import docker_manager
from auth_manager import get_config_value, set_config_value
from db import get_db
from logger import get_logger

log = get_logger("settings_manager")

ENV_FILE = Path(os.getenv("CSCM_ENV_FILE", "/app/cscm.env"))

# Only these keys can be read or written through the API.
PUBLIC_KEYS = (
    "PLAYIT_EMAIL",
    "PLAYIT_SUBSCRIPTION",
    "PLAYIT_REGION",
    "PLAYIT_AGENT",
    "CLOUDFLARE_ENABLED",
    "CLOUDFLARE_ZONE_ID",
    "CLOUDFLARE_BASE_DOMAIN",
)
SECRET_KEYS = ("PLAYIT_PASSWORD", "PLAYIT_SECRET_KEY", "CLOUDFLARE_API_TOKEN")
EDITABLE_KEYS = PUBLIC_KEYS + SECRET_KEYS

SETUP_KEY = "setup_state"
SETUP_STEPS = ("mode", "playit", "agent", "cloudflare")

AGENT_NAME = "cscm-playit"
AGENT_IMAGE = os.getenv("PLAYIT_AGENT_IMAGE", "ghcr.io/playit-cloud/playit-agent:latest")

_lock = threading.Lock()


# ── .env reading / writing ──────────────────────────────────────────────────

def _parse_value(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return raw[1:-1].replace("\\'", "'")
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        return raw[1:-1]
    # unquoted values may carry an inline comment: KEY=value   # note
    return raw.split(" #", 1)[0].strip()


def _format_line(key: str, value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError(f"{key} must be a single line")
    return "{}='{}'\n".format(key, value.replace("'", "\\'"))


def read_env_file() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_FILE.is_file():
        return values
    for line in ENV_FILE.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, raw = stripped.partition("=")
        values[key.strip()] = _parse_value(raw)
    return values


def env_writable() -> bool:
    return ENV_FILE.is_file() and os.access(ENV_FILE, os.W_OK)


def load_env_file() -> None:
    """Apply the editable keys from .env to this process (hand edits included)."""
    for key, value in read_env_file().items():
        if key in EDITABLE_KEYS:
            os.environ[key] = value


def save(values: dict[str, str | None]) -> None:
    """Write the given keys into .env and apply them. ``None`` means unchanged."""
    updates = {k: v for k, v in values.items() if k in EDITABLE_KEYS and v is not None}
    if not updates:
        return
    if not env_writable():
        raise RuntimeError(
            f"{ENV_FILE} is not available to CSCM. Update CSCM, or edit .env by hand and "
            "run `docker compose restart api`."
        )
    with _lock:
        lines = ENV_FILE.read_text().splitlines(keepends=True)
        pending = dict(updates)
        for i, line in enumerate(lines):
            key = line.split("=", 1)[0].strip()
            if key in pending and not line.lstrip().startswith("#"):
                lines[i] = _format_line(key, pending.pop(key))
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.extend(_format_line(k, v) for k, v in pending.items())
        # write in place: .env is a single-file bind mount, so a rename would
        # detach it from the host file
        with open(ENV_FILE, "w") as fh:
            fh.writelines(lines)
    for key, value in updates.items():
        os.environ[key] = value
    log.info("Settings saved: %s", ", ".join(sorted(updates)))


def public_view() -> dict:
    return {
        "values": {k: os.getenv(k, "") for k in PUBLIC_KEYS},
        "secrets_set": {k: bool(os.getenv(k, "").strip()) for k in SECRET_KEYS},
        "env_writable": env_writable(),
        "agent": agent_status(),
    }


# ── first-run setup progress ────────────────────────────────────────────────

def _has_servers() -> bool:
    try:
        with get_db() as conn:
            return conn.execute("SELECT 1 FROM servers LIMIT 1").fetchone() is not None
    except Exception:
        return False


def setup_state() -> dict:
    raw = get_config_value(SETUP_KEY)
    if raw:
        try:
            state = json.loads(raw)
        except ValueError:
            state = {}
    else:
        # First read: installations from before the dashboard setup already
        # configured everything in .env, so don't send them through the wizard.
        # Decided once and stored, so saving settings during the wizard later
        # can't mark a new installation as done early.
        configured = bool(os.getenv("PLAYIT_EMAIL", "").strip()) or _has_servers()
        state = {
            "completed": configured,
            "mode": "public" if configured and os.getenv("PLAYIT_EMAIL") else ("local" if configured else None),
            "step": "mode",
        }
        set_config_value(SETUP_KEY, json.dumps(state))
    step = state.get("step") if state.get("step") in SETUP_STEPS else "mode"
    mode = state.get("mode") if state.get("mode") in ("public", "local") else None
    return {
        "completed": bool(state.get("completed")),
        "step": step,
        "mode": mode,
        "public_available": mode == "public" and bool(os.getenv("PLAYIT_EMAIL", "").strip()),
    }


def update_setup(step: str | None = None, mode: str | None = None, completed: bool | None = None) -> dict:
    current = setup_state()
    state = {
        "step": step if step in SETUP_STEPS else current["step"],
        "mode": mode if mode in ("public", "local") else current["mode"],
        "completed": current["completed"] if completed is None else bool(completed),
    }
    set_config_value(SETUP_KEY, json.dumps(state))
    return setup_state()


# ── managed Playit agent ────────────────────────────────────────────────────

def _agent_container():
    try:
        return docker_manager._get_client().containers.get(AGENT_NAME)
    except Exception:
        return None


def _compose_agent():
    """An agent from older installs, run as the Compose service `playit`."""
    try:
        found = docker_manager._get_client().containers.list(
            filters={"label": "com.docker.compose.service=playit"}
        )
        return found[0] if found else None
    except Exception:
        return None


def agent_status() -> dict:
    own = _agent_container()
    if own is not None:
        return {"managed": True, "running": own.status == "running", "source": "cscm"}
    compose = _compose_agent()
    if compose is not None:
        return {"managed": True, "running": compose.status == "running", "source": "compose"}
    return {"managed": False, "running": False, "source": None}


def start_agent() -> None:
    secret = os.getenv("PLAYIT_SECRET_KEY", "").strip()
    if not secret:
        raise ValueError("Save the agent's SECRET_KEY first.")
    if _compose_agent() is not None:
        return  # an existing Compose-managed agent already runs with this key
    client = docker_manager._get_client()
    existing = _agent_container()
    if existing is not None:
        existing.remove(force=True)
    client.images.pull(AGENT_IMAGE)
    client.containers.run(
        AGENT_IMAGE,
        name=AGENT_NAME,
        detach=True,
        network_mode="host",
        restart_policy={"Name": "unless-stopped"},
        environment={"SECRET_KEY": secret},
        labels={"cscm.playit": "true"},
    )
    log.info("Playit agent container started")


def stop_agent() -> None:
    existing = _agent_container()
    if existing is not None:
        existing.remove(force=True)
        log.info("Playit agent container removed")


# Pick up hand edits to .env whenever the API starts.
load_env_file()
