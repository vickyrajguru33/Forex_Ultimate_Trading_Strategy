from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional


class StateStore:
    def __init__(self, db_path: str | Path = "scanner_state.db") -> None:
        self.db_path = str(db_path)
        self._initialize()

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    instrument TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    candle_time TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS news_alerts (
                    id TEXT PRIMARY KEY,
                    event_key TEXT NOT NULL,
                    reminder_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def insert_or_ignore_alert(self, alert_id: str, instrument: str, direction: str, candle_time: datetime, payload: str) -> bool:
        candle_iso = candle_time.isoformat(timespec="seconds")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO alerts (id, instrument, direction, candle_time, payload, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (alert_id, instrument, direction, candle_iso, payload, now, now),
            )
            conn.commit()
            return cursor.rowcount > 0

    def mark_delivered(self, alert_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                "UPDATE alerts SET status = 'delivered', updated_at = ? WHERE id = ?",
                (now, alert_id),
            )
            conn.commit()

    def mark_failed(self, alert_id: str, reason: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                "UPDATE alerts SET status = 'failed', updated_at = ? WHERE id = ?",
                (now, alert_id),
            )
            conn.commit()

    def pending_alerts(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE status IN ('pending', 'failed') ORDER BY created_at ASC"
            ).fetchall()
            return rows

    def is_delivered(self, alert_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM alerts WHERE id = ? AND status = 'delivered'",
                (alert_id,),
            ).fetchone()
            return row is not None

    def insert_or_ignore_news_alert(self, alert_id: str, event_key: str, reminder_type: str, payload: str) -> bool:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO news_alerts (id, event_key, reminder_type, payload, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?)
                """,
                (alert_id, event_key, reminder_type, payload, now, now),
            )
            conn.commit()
            return cursor.rowcount > 0

    def mark_news_delivered(self, alert_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                "UPDATE news_alerts SET status = 'delivered', updated_at = ? WHERE id = ?",
                (now, alert_id),
            )
            conn.commit()

    def mark_news_failed(self, alert_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                "UPDATE news_alerts SET status = 'failed', updated_at = ? WHERE id = ?",
                (now, alert_id),
            )
            conn.commit()

    def is_news_delivered(self, alert_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM news_alerts WHERE id = ? AND status = 'delivered'",
                (alert_id,),
            ).fetchone()
            return row is not None

    def get_alert(self, alert_id: str) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
