"""
Centralized logging configuration for the CSCM Tool.

Usage:
    from logger import get_logger
    log = get_logger(__name__)
    log.info("Server created")
    log.debug("Response: %s", data)
    log.warning("Tunnel port not found")
    log.error("PlayIT tunnel creation failed: %s", err)

Log level is controlled via the LOG_LEVEL environment variable (default: INFO).
"""

import logging
import os
import sys


# ANSI color codes
class _Color:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    GREY    = "\033[38;5;245m"
    CYAN    = "\033[36m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    RED     = "\033[31m"
    RED_BOLD = "\033[1;31m"
    BLUE    = "\033[34m"


_LEVEL_COLORS = {
    logging.DEBUG:    _Color.GREY,
    logging.INFO:     _Color.CYAN,
    logging.WARNING:  _Color.YELLOW,
    logging.ERROR:    _Color.RED,
    logging.CRITICAL: _Color.RED_BOLD,
}

_LEVEL_LABELS = {
    logging.DEBUG:    "DEBUG   ",
    logging.INFO:     "INFO    ",
    logging.WARNING:  "WARNING ",
    logging.ERROR:    "ERROR   ",
    logging.CRITICAL: "CRITICAL",
}


class _ColorFormatter(logging.Formatter):
    """Log formatter that applies ANSI color codes based on log level."""

    def __init__(self, use_color: bool = True):
        super().__init__()
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        color = _LEVEL_COLORS.get(record.levelno, _Color.RESET)
        label = _LEVEL_LABELS.get(record.levelno, record.levelname)

        # Timestamp
        ts = self.formatTime(record, "%Y-%m-%d %H:%M:%S")

        # Module name (truncated to 20 chars for alignment)
        module = record.name[-20:] if len(record.name) > 20 else record.name.ljust(20)

        message = record.getMessage()

        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)

        if self.use_color:
            return (
                f"{_Color.DIM}{ts}{_Color.RESET} "
                f"{color}{label}{_Color.RESET} "
                f"{_Color.BLUE}{module}{_Color.RESET} "
                f"{message}"
            )
        return f"{ts} {label} {module} {message}"


def _supports_color() -> bool:
    """Return True if the current terminal supports ANSI color codes."""
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(_ColorFormatter(use_color=_supports_color()))

_root = logging.getLogger("cscm")
_root.addHandler(_handler)
_root.propagate = False


def configure(level: str | None = None) -> None:
    """Set the global log level. Reads LOG_LEVEL from env if level is not given."""
    raw = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    numeric = getattr(logging, raw, logging.INFO)
    _root.setLevel(numeric)


# Apply level from env at import time
configure()


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the 'cscm' namespace."""
    return _root.getChild(name)
