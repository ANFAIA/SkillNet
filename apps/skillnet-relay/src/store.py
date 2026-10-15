"""SQLite storage for reports, receipts and rate-limit counts.

One file, no server: the relay handles a trickle of reports, and the counters the limits need
are just queries on ``created_at``. Calls are short and synchronous on purpose.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import closing
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    receipt TEXT PRIMARY KEY,
    instance_id TEXT NOT NULL,
    ip_hash TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    page_path TEXT,
    environment TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    verdict TEXT,
    issue_url TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_created ON reports (created_at);
CREATE INDEX IF NOT EXISTS idx_reports_instance ON reports (instance_id, created_at);
CREATE INDEX IF NOT EXISTS idx_reports_ip ON reports (ip_hash, created_at);
CREATE INDEX IF NOT EXISTS idx_reports_issue ON reports (issue_url);
"""

DAY = 86400.0
HOUR = 3600.0


class Store:
    def __init__(self, path: str) -> None:
        self.path = path
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _one(self, sql: str, args: tuple = ()) -> sqlite3.Row | None:
        with closing(self._conn()) as conn:
            return conn.execute(sql, args).fetchone()

    def _run(self, sql: str, args: tuple = ()) -> None:
        with closing(self._conn()) as conn, conn:
            conn.execute(sql, args)

    # -- limits ---------------------------------------------------------------------------
    def count_global(self, since: float | None = None) -> int:
        since = time.time() - DAY if since is None else since
        row = self._one("SELECT COUNT(*) AS n FROM reports WHERE created_at >= ?", (since,))
        return int(row["n"])

    def count_instance(self, instance_id: str) -> int:
        row = self._one(
            "SELECT COUNT(*) AS n FROM reports WHERE instance_id = ? AND created_at >= ?",
            (instance_id, time.time() - DAY),
        )
        return int(row["n"])

    def count_ip(self, ip_hash: str) -> int:
        row = self._one(
            "SELECT COUNT(*) AS n FROM reports WHERE ip_hash = ? AND created_at >= ?",
            (ip_hash, time.time() - HOUR),
        )
        return int(row["n"])

    def count_for_issue(self, issue_url: str) -> int:
        row = self._one("SELECT COUNT(*) AS n FROM reports WHERE issue_url = ?", (issue_url,))
        return int(row["n"])

    # -- reports --------------------------------------------------------------------------
    def find_duplicate(self, instance_id: str, text_hash: str) -> str | None:
        """The receipt of the same text sent by the same instance in the last day."""
        row = self._one(
            "SELECT receipt FROM reports WHERE instance_id = ? AND text_hash = ? "
            "AND created_at >= ?",
            (instance_id, text_hash, time.time() - DAY),
        )
        return row["receipt"] if row else None

    def insert(self, **fields: Any) -> None:
        fields.setdefault("created_at", time.time())
        columns = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        self._run(f"INSERT INTO reports ({columns}) VALUES ({marks})", tuple(fields.values()))

    def get(self, receipt: str) -> dict[str, Any] | None:
        row = self._one("SELECT * FROM reports WHERE receipt = ?", (receipt,))
        if row is None:
            return None
        data = dict(row)
        data["verdict"] = json.loads(data["verdict"]) if data["verdict"] else None
        return data

    def update(self, receipt: str, **fields: Any) -> None:
        if "verdict" in fields and fields["verdict"] is not None:
            fields["verdict"] = json.dumps(fields["verdict"], ensure_ascii=False)
        sets = ", ".join(f"{k} = ?" for k in fields)
        self._run(f"UPDATE reports SET {sets} WHERE receipt = ?", (*fields.values(), receipt))

    def stale_queued(self, older_than_seconds: float) -> list[str]:
        """Reports still waiting after a restart: they are judged again at startup."""
        with closing(self._conn()) as conn:
            rows = conn.execute(
                "SELECT receipt FROM reports WHERE status = 'queued' AND created_at < ?",
                (time.time() - older_than_seconds,),
            ).fetchall()
        return [r["receipt"] for r in rows]

    def purge_raw(self, retention_days: int) -> None:
        """Blank the text of old reports; the verdict and the issue link stay."""
        self._run(
            "UPDATE reports SET title = '', body = '', page_path = NULL, environment = NULL "
            "WHERE created_at < ? AND body != ''",
            (time.time() - retention_days * DAY,),
        )
