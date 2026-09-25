"""Check GitHub for a newer CSCM version and update this installation in place.

Versions come from ``backend/VERSION``: the running copy is baked into the API
image, the latest one is read from the repository's main branch on GitHub.
Publishing an update therefore means bumping that file on main.

The API can't update itself (it gets replaced halfway), so ``start_update``
launches a short-lived helper container through the Docker socket. The helper
mounts the installation directory at the same path as on the host, runs
``git pull --ff-only`` and ``docker compose up --build -d`` for this Compose
project, and writes its progress into the API's data directory, where the new
API reads it back. ``.env``, the database and world data are never touched.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path

import requests

import docker_manager
from logger import get_logger

log = get_logger("update_manager")

REPO = os.getenv("CSCM_UPDATE_REPO", "lephorx/CSCM")
BRANCH = os.getenv("CSCM_UPDATE_BRANCH", "main")
LATEST_URL = os.getenv(
    "CSCM_UPDATE_URL", f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/backend/VERSION"
)
CHECK_INTERVAL = 60 * 60  # seconds between GitHub checks

UPDATER_NAME = "cscm-updater"
UPDATER_IMAGE = os.getenv("CSCM_UPDATER_IMAGE", "docker:cli")
DATA_DIR = Path(os.getenv("DB_PATH", "/app/data/cscm.db")).parent
STATE_FILE = DATA_DIR / "update.state"
LOG_FILE = DATA_DIR / "update.log"

_VERSION_FILE = Path(__file__).with_name("VERSION")
_cache: dict = {"checked_at": 0.0, "latest": None, "error": None}
_cache_lock = threading.Lock()

# Runs inside the helper container (docker:cli, Alpine).
UPDATE_SCRIPT = r"""
set -eu
S=/cscm-status
log() { printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*" >> "$S/update.log"; }
fail() { log "Update failed: $*"; echo failed > "$S/update.state"; exit 1; }
echo running > "$S/update.state"
log "Preparing the update…"
apk add --no-cache git >/dev/null 2>&1 || fail "could not install git in the update helper"
git config --global --add safe.directory "$CSCM_DIR"
cd "$CSCM_DIR" || fail "installation directory $CSCM_DIR not found"
owner=$(stat -c '%u:%g' .)
log "Downloading the new version from GitHub…"
git pull --ff-only >> "$S/update.log" 2>&1 \
  || fail "git pull failed. Local changes in $CSCM_DIR can block the update; see the help page."
chown -R "$owner" . 2>/dev/null || true
log "Rebuilding and restarting CSCM. This takes a few minutes…"
docker compose --progress plain -p "$CSCM_PROJECT" up --build -d >> "$S/update.log" 2>&1 \
  || fail "docker compose could not rebuild CSCM"
log "Update finished."
echo done > "$S/update.state"
"""


def current_version() -> str:
    try:
        return _VERSION_FILE.read_text().strip()
    except OSError:
        return "0.0.0"


def _parse(version: str) -> tuple[int, ...]:
    parts = []
    for piece in version.strip().lstrip("v").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(latest: str, current: str) -> bool:
    return _parse(latest) > _parse(current)


def latest_version(force: bool = False) -> tuple[str | None, str | None]:
    """Return (latest_version, error), asking GitHub at most once an hour."""
    with _cache_lock:
        if not force and time.time() - _cache["checked_at"] < CHECK_INTERVAL:
            return _cache["latest"], _cache["error"]
        try:
            res = requests.get(LATEST_URL, timeout=10)
            res.raise_for_status()
            _cache.update(latest=res.text.strip(), error=None)
        except requests.RequestException as exc:
            log.warning("Update check failed: %s", exc)
            _cache["error"] = "Could not reach GitHub to check for updates"
        _cache["checked_at"] = time.time()
        return _cache["latest"], _cache["error"]


def _own_container():
    """The API container itself; its Compose labels tell us what to rebuild."""
    return docker_manager._get_client().containers.get(socket.gethostname())


def install_info() -> tuple[dict | None, str | None]:
    """Return ({project, working_dir, data_dir}, None) or (None, reason)."""
    try:
        me = _own_container()
    except Exception:
        return None, "CSCM is not running in Docker Compose, so it can't update itself."
    labels = me.labels or {}
    project = labels.get("com.docker.compose.project")
    working_dir = labels.get("com.docker.compose.project.working_dir")
    data_dir = next(
        (m.get("Source") for m in me.attrs.get("Mounts", []) if m.get("Destination") == str(DATA_DIR)),
        None,
    )
    if not (project and working_dir and data_dir):
        return None, "This installation wasn't started with Docker Compose, so it can't update itself."
    return {"project": project, "working_dir": working_dir, "data_dir": data_dir}, None


def _updater():
    try:
        return docker_manager._get_client().containers.get(UPDATER_NAME)
    except Exception:
        return None


def status() -> dict:
    state = STATE_FILE.read_text().strip() if STATE_FILE.exists() else "idle"
    lines = LOG_FILE.read_text().splitlines()[-40:] if LOG_FILE.exists() else []
    updater = _updater()
    running = updater is not None and updater.status in ("created", "running")
    # The helper died without reporting back (e.g. Docker restarted).
    if state == "running" and not running:
        state = "failed"
    return {"state": state, "running": running, "log": lines, "version": current_version()}


def start_update() -> tuple[bool, str]:
    info, reason = install_info()
    if not info:
        return False, reason

    existing = _updater()
    if existing is not None:
        if existing.status in ("created", "running"):
            return False, "An update is already running."
        existing.remove(force=True)

    client = docker_manager._get_client()
    try:
        client.images.get(UPDATER_IMAGE)
    except Exception:
        log.info("Pulling update helper image %s", UPDATER_IMAGE)
        repo, _, tag = UPDATER_IMAGE.partition(":")
        client.images.pull(repo, tag=tag or "latest")

    STATE_FILE.write_text("running\n")
    LOG_FILE.write_text("")

    wd = info["working_dir"]
    client.containers.run(
        UPDATER_IMAGE,
        ["sh", "-c", UPDATE_SCRIPT],
        name=UPDATER_NAME,
        detach=True,
        labels={"cscm.updater": "true"},
        environment={"CSCM_DIR": wd, "CSCM_PROJECT": info["project"]},
        working_dir=wd,
        volumes={
            "/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"},
            wd: {"bind": wd, "mode": "rw"},
            info["data_dir"]: {"bind": "/cscm-status", "mode": "rw"},
        },
    )
    log.info("Update started: project=%s dir=%s", info["project"], wd)
    return True, "Update started"
