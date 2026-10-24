"""
==============================================================================
Module: agents.memory
Role in Architecture: Persistent Conversation History & Student Preferences
==============================================================================
Manages SQLite persistence for:
1. Multi-turn chat history (`chat_history` table):
   Injected into context so the assistant remembers past turns (last N turns).
2. Student preferences (`user_preferences` table):
   Stores profile details like student name, university email, and reminder lead times.

Academic Review Defense:
Maintains continuity in long-running planning tasks without relying on expensive
vector DB storage for short-term conversation state.
"""

from __future__ import annotations
import datetime
import sqlite3
from typing import Any, Dict, List, Optional
from app.config import settings


def get_memory_db() -> sqlite3.Connection:
    """Returns a SQLite connection for agent memory."""
    db_path = settings.SQLITE_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_memory_tables() -> None:
    """Initializes chat_history and user_preferences tables."""
    conn = get_memory_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            pref_key TEXT PRIMARY KEY,
            pref_value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    # Seed default student preferences from configuration if not already set
    default_prefs = {
        "name": settings.USER_NAME,
        "email": settings.USER_DEFAULT_EMAIL,
        "default_reminder_lead_hours": str(settings.DEFAULT_REMINDER_LEAD_HOURS),
    }

    for key, val in default_prefs.items():
        cursor.execute(
            "INSERT OR IGNORE INTO user_preferences (pref_key, pref_value) VALUES (?, ?)",
            (key, val),
        )

    conn.commit()
    conn.close()


init_memory_tables()


class ConversationMemory:
    """Interface for saving and querying conversation history and student preferences."""

    @staticmethod
    def add_turn(session_id: str, role: str, content: str) -> None:
        """Appends a new turn to the session history."""
        conn = get_memory_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_history (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def get_recent_history(session_id: str, last_n: int = 6) -> List[Dict[str, str]]:
        """
        Retrieves the last N conversation turns for context injection.
        Returns list of dicts: [{"role": "user"|"assistant", "content": "..."}]
        """
        conn = get_memory_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT role, content FROM chat_history
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, last_n),
        )
        rows = cursor.fetchall()
        conn.close()

        # Reverse so messages are chronological (oldest to newest)
        history = [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
        return history

    @staticmethod
    def clear_session(session_id: str) -> None:
        """Clears all turns for a specific session."""
        conn = get_memory_db()
        conn.execute("DELETE FROM chat_history WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def get_preference(key: str, default: str = "") -> str:
        """Retrieves a student profile preference."""
        conn = get_memory_db()
        cursor = conn.cursor()
        cursor.execute("SELECT pref_value FROM user_preferences WHERE pref_key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row["pref_value"] if row else default

    @staticmethod
    def set_preference(key: str, value: str) -> None:
        """Updates or sets a student profile preference."""
        conn = get_memory_db()
        conn.execute(
            "INSERT OR REPLACE INTO user_preferences (pref_key, pref_value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (key, value),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def get_all_preferences() -> Dict[str, str]:
        """Returns all configured preferences as a dictionary."""
        conn = get_memory_db()
        cursor = conn.cursor()
        cursor.execute("SELECT pref_key, pref_value FROM user_preferences")
        rows = cursor.fetchall()
        conn.close()
        return {row["pref_key"]: row["pref_value"] for row in rows}
