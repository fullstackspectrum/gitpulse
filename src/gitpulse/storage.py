"""SQLite persistence for collected traffic snapshots."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def default_db_path() -> Path:
    configured = os.getenv("GITPULSE_DB")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".local" / "share" / "gitpulse" / "gitpulse.sqlite3"


class SnapshotStore:
    """Store timestamped GitHub traffic responses locally."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY,
                    owner TEXT NOT NULL,
                    repo TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )"""
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_snapshots_repo_metric "
                "ON snapshots(owner, repo, metric, fetched_at)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def save(self, owner: str, repo: str, metric: str, payload: dict[str, Any]) -> None:
        fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO snapshots(owner, repo, metric, fetched_at, payload) VALUES (?, ?, ?, ?, ?)",
                (owner, repo, metric, fetched_at, json.dumps(payload)),
            )

    def history(self, owner: str, repo: str, metric: str, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT fetched_at, payload FROM snapshots
                   WHERE owner = ? AND repo = ? AND metric = ?
                   ORDER BY fetched_at DESC, id DESC LIMIT ?""",
                (owner, repo, metric, limit),
            ).fetchall()
        return [{"fetched_at": stamp, **json.loads(payload)} for stamp, payload in reversed(rows)]
