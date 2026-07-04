"""Backup creation, restore, retention, and cron-based scheduling.

Three backup strategies are supported:

  zip   — Compressed archive (.zip) stored under BACKUPS_DIR/<server_id>/.
          Portable and self-contained; slower for large worlds.

  copy  — Plain directory copy stored under BACKUPS_DIR/<server_id>/.
          Faster than zip (no compression); uses more disk space.

  zfs   — Instant ZFS snapshot of the server's dataset.
          Requires ZFS on the host and ZFS_DATASET_BASE to be set.
          The CSCM container needs the `zfs` binary (mount /sbin/zfs into
          the container) and /dev/zfs, plus the zfs/zpool privilege.
          Each server must live on its own ZFS dataset:
            <ZFS_DATASET_BASE>/<server_id>
          e.g. ZFS_DATASET_BASE=tank/cscm/servers → tank/cscm/servers/3

Scheduling is handled by an in-process APScheduler BackgroundScheduler —
cron triggers are loaded from the backup_schedules table and re-synced
whenever a schedule is created, updated, or deleted.
"""

import os
import shutil
import subprocess
import tempfile
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

# Interval in seconds for the background save-all flush that keeps playerdata
# files on disk current while players are online.  0 = disabled.
PLAYER_DATA_FLUSH_INTERVAL = int(os.getenv("PLAYER_DATA_FLUSH_INTERVAL", "60"))

# Optional: base ZFS dataset under which each server has its own child dataset.
# Example: ZFS_DATASET_BASE=tank/cscm/servers  →  server 3 uses tank/cscm/servers/3
ZFS_DATASET_BASE = os.getenv("ZFS_DATASET_BASE", "").rstrip("/")

BACKUP_TYPE_ZIP  = "zip"
BACKUP_TYPE_COPY = "copy"
BACKUP_TYPE_ZFS  = "zfs"
BACKUP_TYPES     = (BACKUP_TYPE_ZIP, BACKUP_TYPE_COPY, BACKUP_TYPE_ZFS)

_scheduler: BackgroundScheduler | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _server_backups_dir(server_id: int) -> Path:
    path = Path(BACKUPS_DIR) / str(server_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _migrate_db() -> None:
    """Add backup_type columns to backups and backup_schedules if missing (schema v2)."""
    with get_db() as conn:
        existing_backup_cols = {row[1] for row in conn.execute("PRAGMA table_info(backups)").fetchall()}
        if "backup_type" not in existing_backup_cols:
            conn.execute("ALTER TABLE backups ADD COLUMN backup_type TEXT NOT NULL DEFAULT 'zip'")
            log.info("DB migration: added backups.backup_type column")

        existing_sched_cols = {row[1] for row in conn.execute("PRAGMA table_info(backup_schedules)").fetchall()}
        if "backup_type" not in existing_sched_cols:
            conn.execute("ALTER TABLE backup_schedules ADD COLUMN backup_type TEXT NOT NULL DEFAULT 'zip'")
            log.info("DB migration: added backup_schedules.backup_type column")


# ---------------------------------------------------------------------------
# ZFS helpers
# ---------------------------------------------------------------------------

def _zfs_run(args: list[str], timeout: int = 60) -> tuple[int, str, str]:
    """Run a zfs subcommand. Returns (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(["zfs", *args], capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return 1, "", "zfs binary not found — mount /sbin/zfs into the container and expose /dev/zfs"
    except subprocess.TimeoutExpired:
        return 1, "", f"zfs command timed out after {timeout}s"


def _zfs_dataset(server_id: int) -> str | None:
    if not ZFS_DATASET_BASE:
        return None
    return f"{ZFS_DATASET_BASE}/{server_id}"


def _zfs_snapshot_size(snapshot: str) -> int:
    rc, out, _ = _zfs_run(["list", "-t", "snapshot", "-p", "-o", "referenced", "-H", snapshot])
    if rc == 0:
        try:
            return int(out)
        except ValueError:
            pass
    return 0


# ---------------------------------------------------------------------------
# Per-type creation helpers
# ---------------------------------------------------------------------------

def _create_zip_backup(data_dir: Path, dest_dir: Path, timestamp: str) -> dict:
    filename = f"backup-{timestamp}.zip"
    dest = dest_dir / filename
    try:
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for fp in data_dir.rglob("*"):
                if fp.is_file():
                    zf.write(fp, fp.relative_to(data_dir))
    except Exception as exc:
        dest.unlink(missing_ok=True)
        return {"success": False, "message": f"Zip creation failed: {exc}"}
    return {"success": True, "filename": filename, "size_bytes": dest.stat().st_size}


def _create_copy_backup(data_dir: Path, dest_dir: Path, timestamp: str) -> dict:
    dirname = f"backup-copy-{timestamp}"
    dest = dest_dir / dirname
    try:
        shutil.copytree(str(data_dir), str(dest))
    except Exception as exc:
        shutil.rmtree(dest, ignore_errors=True)
        return {"success": False, "message": f"Copy backup failed: {exc}"}
    size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
    return {"success": True, "filename": dirname, "size_bytes": size}


def _create_zfs_backup(server_id: int, timestamp: str) -> dict:
    dataset = _zfs_dataset(server_id)
    if not dataset:
        return {"success": False, "message": "ZFS_DATASET_BASE is not configured"}
    rc, _, stderr = _zfs_run(["list", dataset])
    if rc != 0:
        return {"success": False, "message": f"ZFS dataset '{dataset}' not found: {stderr}"}
    snapshot = f"{dataset}@cscm-{timestamp}"
    rc, _, stderr = _zfs_run(["snapshot", snapshot])
    if rc != 0:
        return {"success": False, "message": f"zfs snapshot failed: {stderr}"}
    return {"success": True, "filename": snapshot, "size_bytes": _zfs_snapshot_size(snapshot)}


# ---------------------------------------------------------------------------
# Public backup API
# ---------------------------------------------------------------------------

def create_backup(server_id: int, kind: str = "manual", backup_type: str = BACKUP_TYPE_ZIP) -> dict:
    if backup_type not in BACKUP_TYPES:
        return {"success": False, "message": f"Unknown backup type '{backup_type}'. Valid: {', '.join(BACKUP_TYPES)}"}

    data_dir = Path(server_data_dir(server_id))
    if backup_type != BACKUP_TYPE_ZFS and not data_dir.exists():
        return {"success": False, "message": "Server data directory not found"}

    running = docker_manager.runtime_status(server_id) not in ("not_created", "stopped")
    if running:
        try:
            docker_manager.send_rcon(server_id, "save-off")
            docker_manager.send_rcon(server_id, "save-all flush")
            time.sleep(2 if backup_type != BACKUP_TYPE_ZFS else 1)
        except Exception as exc:
            log.warning("Could not flush world before backup server_id=%d: %s", server_id, exc)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest_dir  = _server_backups_dir(server_id)

    try:
        if backup_type == BACKUP_TYPE_ZIP:
            result = _create_zip_backup(data_dir, dest_dir, timestamp)
        elif backup_type == BACKUP_TYPE_COPY:
            result = _create_copy_backup(data_dir, dest_dir, timestamp)
        else:
            result = _create_zfs_backup(server_id, timestamp)
    finally:
        if running:
            try:
                docker_manager.send_rcon(server_id, "save-on")
            except Exception as exc:
                log.warning("Could not re-enable saving after backup server_id=%d: %s", server_id, exc)

    if not result["success"]:
        return result

    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO backups (server_id, filename, size_bytes, kind, backup_type)"
            " VALUES (?, ?, ?, ?, ?)",
            (server_id, result["filename"], result["size_bytes"], kind, backup_type),
        )
        backup_id = cur.lastrowid

    log.info(
        "Backup created: server_id=%d filename=%s type=%s size=%d",
        server_id, result["filename"], backup_type, result["size_bytes"],
    )
    return {
        "success":     True,
        "backup_id":   backup_id,
        "filename":    result["filename"],
        "size_bytes":  result["size_bytes"],
        "backup_type": backup_type,
    }


def list_backups(server_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, filename, size_bytes, created_at, kind, backup_type FROM backups"
            " WHERE server_id = ? ORDER BY created_at DESC",
            (server_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_backup_path(server_id: int, backup_id: int) -> Path | None:
    """Return path for zip/copy backups; None for ZFS or missing."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT filename, backup_type FROM backups WHERE id = ? AND server_id = ?",
            (backup_id, server_id),
        ).fetchone()
    if not row:
        return None
    btype = row["backup_type"] or BACKUP_TYPE_ZIP
    if btype == BACKUP_TYPE_ZFS:
        return None
    path = _server_backups_dir(server_id) / row["filename"]
    return path if path.exists() else None


def get_backup_download_archive(server_id: int, backup_id: int) -> tuple[Path | None, bool, str | None]:
    """Return (path, needs_cleanup_after_send, error_message).

    - zip:  returns the archive path directly (no cleanup needed).
    - copy: creates a temporary zip on the fly; caller must delete after send.
    - zfs:  not downloadable as a file; returns an error message.
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT filename, backup_type FROM backups WHERE id = ? AND server_id = ?",
            (backup_id, server_id),
        ).fetchone()
    if not row:
        return None, False, "Backup not found"

    btype    = row["backup_type"] or BACKUP_TYPE_ZIP
    filename = row["filename"]

    if btype == BACKUP_TYPE_ZFS:
        return None, False, (
            "ZFS snapshots cannot be downloaded as a file. "
            "Use the restore endpoint to roll back the dataset, or run "
            "'zfs send <snapshot> | gzip > backup.zfs.gz' on the host directly."
        )

    path = _server_backups_dir(server_id) / filename

    if btype == BACKUP_TYPE_ZIP:
        if not path.exists():
            return None, False, "Backup archive not found on disk"
        return path, False, None

    # BACKUP_TYPE_COPY — create a temporary zip from the directory
    if not path.exists():
        return None, False, "Backup directory not found on disk"
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".zip")
        os.close(tmp_fd)
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fp in path.rglob("*"):
                if fp.is_file():
                    zf.write(fp, fp.relative_to(path))
    except Exception as exc:
        Path(tmp_path).unlink(missing_ok=True)
        return None, False, f"Failed to create download archive: {exc}"
    return Path(tmp_path), True, None


def delete_backup(server_id: int, backup_id: int) -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT filename, backup_type FROM backups WHERE id = ? AND server_id = ?",
            (backup_id, server_id),
        ).fetchone()
        if not row:
            return {"success": False, "message": "Backup not found"}
        conn.execute("DELETE FROM backups WHERE id = ?", (backup_id,))

    btype    = row["backup_type"] or BACKUP_TYPE_ZIP
    filename = row["filename"]

    if btype == BACKUP_TYPE_ZIP:
        (_server_backups_dir(server_id) / filename).unlink(missing_ok=True)
    elif btype == BACKUP_TYPE_COPY:
        p = _server_backups_dir(server_id) / filename
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
    elif btype == BACKUP_TYPE_ZFS:
        rc, _, stderr = _zfs_run(["destroy", filename])
        if rc != 0:
            log.warning("Failed to destroy ZFS snapshot %s: %s", filename, stderr)

    return {"success": True, "message": "Backup deleted"}


def restore_backup(server_id: int, backup_id: int) -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT filename, backup_type FROM backups WHERE id = ? AND server_id = ?",
            (backup_id, server_id),
        ).fetchone()
    if not row:
        return {"success": False, "message": "Backup not found"}

    btype    = row["backup_type"] or BACKUP_TYPE_ZIP
    filename = row["filename"]
    data_dir = Path(server_data_dir(server_id))
    base     = os.path.realpath(docker_manager.SERVERS_DIR)

    if btype != BACKUP_TYPE_ZFS and not os.path.realpath(data_dir).startswith(base):
        return {"success": False, "message": "Refusing to restore outside SERVERS_DIR"}

    docker_manager.stop_server(server_id)

    if btype == BACKUP_TYPE_ZIP:
        archive = _server_backups_dir(server_id) / filename
        if not archive.exists():
            docker_manager.start_server(server_id)
            return {"success": False, "message": "Backup archive missing on disk"}
        shutil.rmtree(data_dir, ignore_errors=True)
        data_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(data_dir)

    elif btype == BACKUP_TYPE_COPY:
        src = _server_backups_dir(server_id) / filename
        if not src.exists():
            docker_manager.start_server(server_id)
            return {"success": False, "message": "Backup directory missing on disk"}
        shutil.rmtree(data_dir, ignore_errors=True)
        shutil.copytree(str(src), str(data_dir))

    elif btype == BACKUP_TYPE_ZFS:
        rc, _, stderr = _zfs_run(["rollback", "-r", filename])
        if rc != 0:
            docker_manager.start_server(server_id)
            return {"success": False, "message": f"zfs rollback failed: {stderr}"}

    docker_manager.start_server(server_id)
    log.info("Backup restored: server_id=%d backup_id=%d type=%s", server_id, backup_id, btype)
    return {"success": True, "message": f"Backup restored ({btype}), server restarting"}


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


def _run_scheduled_backup(server_id: int, retention: int, backup_type: str) -> None:
    try:
        create_backup(server_id, kind="scheduled", backup_type=backup_type)
        prune(server_id, retention)
    except Exception as exc:
        log.error("Scheduled backup failed server_id=%d: %s", server_id, exc)


def _run_periodic_save_all() -> None:
    """Call save-all flush on every healthy running server.

    Keeps world/playerdata/<uuid>.dat and world/stats/<uuid>.json files
    up to date on disk so API reads return current data.
    """
    try:
        with get_db() as conn:
            rows = conn.execute("SELECT id FROM servers WHERE status = 'created'").fetchall()
        for row in rows:
            sid = row["id"]
            if docker_manager.runtime_status(sid) in ("healthy", "running"):
                try:
                    docker_manager.send_rcon(sid, "save-all flush")
                    log.debug("Periodic save-all flush: server_id=%d", sid)
                except Exception as exc:
                    log.debug("Periodic flush failed for server_id=%d: %s", sid, exc)
    except Exception as exc:
        log.error("Periodic save-all task error: %s", exc)


def init_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _migrate_db()
    _scheduler = BackgroundScheduler()
    _scheduler.start()

    with get_db() as conn:
        schedules = conn.execute(
            "SELECT server_id, cron, retention, backup_type FROM backup_schedules WHERE enabled = 1"
        ).fetchall()
    for s in schedules:
        _add_job(s["server_id"], s["cron"], s["retention"], s["backup_type"] or BACKUP_TYPE_ZIP)

    if PLAYER_DATA_FLUSH_INTERVAL > 0:
        _scheduler.add_job(
            _run_periodic_save_all,
            "interval",
            seconds=PLAYER_DATA_FLUSH_INTERVAL,
            id="periodic-save-all",
            replace_existing=True,
        )
        log.info(
            "Backup scheduler started with %d active schedule(s); periodic save-all every %ds",
            len(schedules), PLAYER_DATA_FLUSH_INTERVAL,
        )
    else:
        log.info("Backup scheduler started with %d active schedule(s)", len(schedules))


def _add_job(server_id: int, cron: str, retention: int, backup_type: str) -> None:
    trigger = CronTrigger.from_crontab(cron)
    _scheduler.add_job(
        _run_scheduled_backup,
        trigger=trigger,
        args=[server_id, retention, backup_type],
        id=_job_id(server_id),
        replace_existing=True,
    )


def set_schedule(
    server_id: int,
    cron: str,
    retention: int = 5,
    enabled: bool = True,
    backup_type: str = BACKUP_TYPE_ZIP,
) -> dict:
    if backup_type not in BACKUP_TYPES:
        return {"success": False, "message": f"Unknown backup type '{backup_type}'. Valid: {', '.join(BACKUP_TYPES)}"}
    try:
        CronTrigger.from_crontab(cron)
    except ValueError as exc:
        return {"success": False, "message": f"Invalid cron expression: {exc}"}

    with get_db() as conn:
        conn.execute(
            "INSERT INTO backup_schedules (server_id, cron, retention, enabled, backup_type)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(server_id) DO UPDATE SET cron=excluded.cron,"
            " retention=excluded.retention, enabled=excluded.enabled,"
            " backup_type=excluded.backup_type",
            (server_id, cron, retention, int(enabled), backup_type),
        )

    if _scheduler is not None:
        if enabled:
            _add_job(server_id, cron, retention, backup_type)
        elif _scheduler.get_job(_job_id(server_id)):
            _scheduler.remove_job(_job_id(server_id))

    return {"success": True, "message": "Backup schedule saved"}


def get_schedule(server_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT cron, retention, enabled, backup_type FROM backup_schedules WHERE server_id = ?",
            (server_id,),
        ).fetchone()
    return dict(row) if row else None


def delete_schedule(server_id: int) -> dict:
    with get_db() as conn:
        conn.execute("DELETE FROM backup_schedules WHERE server_id = ?", (server_id,))
    if _scheduler is not None and _scheduler.get_job(_job_id(server_id)):
        _scheduler.remove_job(_job_id(server_id))
    return {"success": True, "message": "Backup schedule removed"}
