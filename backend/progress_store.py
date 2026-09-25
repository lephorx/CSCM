"""Thread-safe in-memory store for server provisioning/deletion progress.

Keyed by server_id (int).  Each entry holds the latest status so any
Flask worker thread can read it independently of the thread running the
long operation.
"""

import threading
from datetime import datetime, UTC

_lock = threading.Lock()
_store: dict[int, dict] = {}


def update(
    server_id: int,
    *,
    action: str,
    percent: int,
    step: str,
    status: str = "in_progress",
    message: str | None = None,
) -> None:
    """Write or overwrite the progress entry for server_id."""
    with _lock:
        _store[server_id] = {
            "server_id": server_id,
            "action": action,
            "status": status,
            "percent": min(100, max(0, percent)),
            "step": step,
            "message": message,
            "updated_at": datetime.now(UTC).isoformat(),
        }


def get(server_id: int) -> dict:
    """Return the current progress for server_id, or an 'idle' default."""
    with _lock:
        return dict(
            _store.get(
                server_id,
                {
                    "server_id": server_id,
                    "action": None,
                    "status": "idle",
                    "percent": 0,
                    "step": None,
                    "message": None,
                    "updated_at": None,
                },
            )
        )


def clear(server_id: int) -> None:
    """Remove the progress entry for server_id."""
    with _lock:
        _store.pop(server_id, None)
