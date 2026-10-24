"""
==============================================================================
Module: mcp_servers.db
Role in Architecture: Persistent SQLite Database Engine for Tool State
==============================================================================
Provides thread-safe persistence for MCP tools:
1. `reminders` table: tracks scheduled alerts, timestamps, and notification statuses.
2. `calendar_events` table: tracks scheduled events, attendees, and .ics file locations.

Design Choice for Review:
Local SQLite eliminates external database dependencies (like PostgreSQL/MySQL),
keeping the entire personal assistant lightweight and self-contained on the student's laptop.
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.config import settings


def get_db_connection() -> sqlite3.Connection:
    """Creates a connection with row-factory enabled for dictionary-like access."""
    db_path = settings.SQLITE_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_tool_tables() -> None:
    """Initializes tables for reminders and calendar events if they do not exist."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Reminders Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            due_datetime TEXT NOT NULL,
            note TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Calendar Events Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS calendar_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            start_datetime TEXT NOT NULL,
            end_datetime TEXT NOT NULL,
            attendees TEXT DEFAULT '',
            description TEXT DEFAULT '',
            ics_path TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# Initialize tables upon module import
init_tool_tables()
