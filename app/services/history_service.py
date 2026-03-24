import sqlite3
from datetime import datetime, timezone
from threading import Lock
from typing import Any


class HistoryService:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS contacts (
                    phone TEXT PRIMARY KEY,
                    escalated INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    @staticmethod
    def _utcnow_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def save_message(self, phone: str, direction: str, content: str, source: str) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO messages (phone, direction, content, source, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (phone, direction, content, source, self._utcnow_iso()),
                )
                conn.commit()

    def set_escalated(self, phone: str, escalated: bool) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO contacts (phone, escalated, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(phone) DO UPDATE SET
                        escalated = excluded.escalated,
                        updated_at = excluded.updated_at
                    """,
                    (phone, 1 if escalated else 0, self._utcnow_iso()),
                )
                conn.commit()

    def is_escalated(self, phone: str) -> bool:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT escalated FROM contacts WHERE phone = ?",
                    (phone,),
                ).fetchone()
                if row is None:
                    return False
                return bool(row["escalated"])

    def get_escalated_contacts(self) -> list[dict[str, Any]]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT
                        c.phone,
                        c.updated_at,
                        (
                            SELECT m.content
                            FROM messages m
                            WHERE m.phone = c.phone
                            ORDER BY m.id DESC
                            LIMIT 1
                        ) AS last_message,
                        (
                            SELECT m.created_at
                            FROM messages m
                            WHERE m.phone = c.phone
                            ORDER BY m.id DESC
                            LIMIT 1
                        ) AS last_message_at
                    FROM contacts c
                    WHERE c.escalated = 1
                    ORDER BY c.updated_at DESC
                    """
                ).fetchall()
                return [dict(row) for row in rows]

    def get_recent_messages(self, phone: str, limit: int = 30) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 100))
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT phone, direction, content, source, created_at
                    FROM messages
                    WHERE phone = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (phone, safe_limit),
                ).fetchall()

                messages = [dict(row) for row in rows]
                messages.reverse()
                return messages

    def get_incoming_count(self, phone: str) -> int:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT COUNT(1) AS total
                    FROM messages
                    WHERE phone = ? AND direction = 'in'
                    """,
                    (phone,),
                ).fetchone()
                if row is None:
                    return 0
                return int(row["total"])
