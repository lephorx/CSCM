"""Backup creation, restore, retention, and cron-based scheduling.

Backups are zip archives of a server's data directory, stored under
BACKUPS_DIR/<server_id>/. Scheduling is handled by an in-process
APScheduler BackgroundScheduler — cron triggers are loaded from the
backup_schedules table and re-synced whenever a schedule is created,
updated, or deleted.
"""

import os
import shutil
import time
import zipfile
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

import docker_manager
from docker_manager import server_data_dir
from db import get_db
from logger import get_logger

load_dotenv()

log = get_logger("backup_manager")

BACKUPS_DIR = os.getenv("BACKUPS_DIR", "/data/backups")

_scheduler: BackgroundScheduler | None = None


def _server_backups_dir(server_id: int) -> Path:
    path = Path(BACKUPS_DIR) / str(server_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_backup(server_id: int, kind: str = "manual") -> dict:
    data_dir = Path(server_data_dir(server_id))
    if not data_dir.exists():
        return {"success": False, "message": "Server data directory not found"}

    running = docker_manager.runtime_status(server_id) not in ("not_created", "stopped")
    if running:
        try:
            docker_manager.send_rcon(server_id, "save-off")
            docker_manager.send_rcon(server_id, "save-all flush")
            time.sleep(2)
        except Exception as exc:
            log.warning("Could not flush world before backup for server_id=%d: %s", server_id, exc)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"backup-{timestamp}.zip"
    dest = _server_backups_dir(server_id) / filename

    try:
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in data_dir.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(data_dir))
    finally:
        if running:
            try:
                docker_manager.send_rcon(server_id, "save-on")
            except Exception as exc:
                log.warning("Could not re-enable saving after backup for server_id=%d: %s", server_id, exc)

    size_bytes = dest.stat().st_size
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO backups (server_id, filename, size_bytes, kind) VALUES (?, ?, ?, ?)",
            (server_id, filename, size_bytes, kind),
        )
        backup_id = cur.lastrowid

    log.info("Backup created: server_id=%d, filename=%s, size=%d bytes", server_id, filename, size_bytes)
    return {"success": True, "backup_id": backup_id, "filename": filename, "size_bytes": size_bytes}


def list_backups(server_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, filename, size_bytes, created_at, kind FROM backups"
            " WHERE server_id = ? ORDER BY created_at DESC",
            (server_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_backup(server_id: int, backup_id: int) -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT filename FROM backups WHERE id = ? AND server_id = ?",
            (backup_id, server_id),
        ).fetchone()
        if not row:
            return {"success": False, "message": "Backup not found"}
        conn.execute("DELETE FROM backups WHERE id = ?", (backup_id,))

    path = _server_backups_dir(server_id) / row["filename"]
    path.unlink(missing_ok=True)
    return {"success": True, "message": "Backup deleted"}


def restore_backup(server_id: int, backup_id: int) -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT filename FROM backups WHERE id = ? AND server_id = ?",
            (backup_id, server_id),
        ).fetchone()
    if not row:
        return {"success": False, "message": "Backup not found"}

    archive = _server_backups_dir(server_id) / row["filename"]
    if not archive.exists():
        return {"success": False, "message": "Backup archive missing on disk"}

    data_dir = Path(server_data_dir(server_id))
    base = os.path.realpath(docker_manager.SERVERS_DIR)
    if not os.path.realpath(data_dir).startswith(base):
        return {"success": False, "message": "Refusing to restore outside SERVERS_DIR"}

    docker_manager.stop_server(server_id)

    shutil.rmtree(data_dir, ignore_errors=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "r") as zf:
        zf.extractall(data_dir)

    docker_manager.start_server(server_id)
    log.info("Backup restored: server_id=%d, backup_id=%d", server_id, backup_id)
    return {"success": True, "message": "Backup restored, server restarting"}


def prune(server_id: int, retention: int) -> None:
    backups = list_backups(server_id)
    scheduled = [b for b in backups if b["kind"] == "scheduled"]
    for stale in scheduled[retention:]:
        delete_backup(server_id, stale["id"])


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

def _job_id(server_id: int) -> str:
    return f"backup-{server_id}"


def _run_scheduled_backup(server_id: int, retention: int) -> None:
    try:
        create_backup(server_id, kind="scheduled")
        prune(server_id, retention)
    except Exception as exc:
        log.error("Scheduled backup failed for server_id=%d: %s", server_id, exc)


def init_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.start()

    with get_db() as conn:
        schedules = conn.execute(
            "SELECT server_id, cron, retention FROM backup_schedules WHERE enabled = 1"
        ).fetchall()
    for s in schedules:
        _add_job(s["server_id"], s["cron"], s["retention"])
    log.info("Backup scheduler started with %d active schedule(s)", len(schedules))


def _add_job(server_id: int, cron: str, retention: int) -> None:
    trigger = CronTrigger.from_crontab(cron)
    _scheduler.add_job(
        _run_scheduled_backup,
        trigger=trigger,
        args=[server_id, retention],
        id=_job_id(server_id),
        replace_existing=True,
    )


def set_schedule(server_id: int, cron: str, retention: int = 5, enabled: bool = True) -> dict:
    try:
        CronTrigger.from_crontab(cron)
    except ValueError as exc:
        return {"success": False, "message": f"Invalid cron expression: {exc}"}

    with get_db() as conn:
        conn.execute(
            "INSERT INTO backup_schedules (server_id, cron, retention, enabled)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT(server_id) DO UPDATE SET cron=excluded.cron,"
            " retention=excluded.retention, enabled=excluded.enabled",
            (server_id, cron, retention, int(enabled)),
        )

    if _scheduler is not None:
        if enabled:
            _add_job(server_id, cron, retention)
        elif _scheduler.get_job(_job_id(server_id)):
            _scheduler.remove_job(_job_id(server_id))

    return {"success": True, "message": "Backup schedule saved"}


def get_schedule(server_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT cron, retention, enabled FROM backup_schedules WHERE server_id = ?",
            (server_id,),
        ).fetchone()
    return dict(row) if row else None


def delete_schedule(server_id: int) -> dict:
    with get_db() as conn:
        conn.execute("DELETE FROM backup_schedules WHERE server_id = ?", (server_id,))
    if _scheduler is not None and _scheduler.get_job(_job_id(server_id)):
        _scheduler.remove_job(_job_id(server_id))
    return {"success": True, "message": "Backup schedule removed"}
