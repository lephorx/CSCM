#!/usr/bin/env python3
"""Initialize the local SQLite database (app tables + auth tables).

Usage:
    python scripts/init_db.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import init_schema, DB_PATH
from auth_manager import initialize_auth_storage


def main() -> None:
    init_schema()
    initialize_auth_storage()
    print(f"Database initialized at {DB_PATH}")


if __name__ == "__main__":
    main()
