"""SQLite operations run in a thread with a separate connection per transaction."""

import asyncio
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from teamstorm_mcp.application.models import StatusReference
from teamstorm_mcp.application.scheduling import ClosureRequest, ScheduledClosure


class SQLiteClosureRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize)

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS scheduled_closures (
                    task_key TEXT PRIMARY KEY,
                    close_at REAL NOT NULL,
                    target_status TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'pending',
                    current_status TEXT,
                    checked_at REAL,
                    revision INTEGER NOT NULL DEFAULT 1
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS due_closures ON scheduled_closures(state, close_at)"
            )
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(scheduled_closures)")
            }
            for name, kind in (
                ("workflow_id", "TEXT"),
                ("workflow_revision", "INTEGER"),
                ("workflow_fingerprint", "TEXT"),
            ):
                if name not in columns:
                    connection.execute(f"ALTER TABLE scheduled_closures ADD COLUMN {name} {kind}")

    async def schedule(self, request: ClosureRequest) -> ScheduledClosure:
        return await asyncio.to_thread(self._schedule, request)

    def _schedule(self, request: ClosureRequest) -> ScheduledClosure:
        with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
            connection.execute(
                """INSERT INTO scheduled_closures(
                       task_key, close_at, target_status,
                       workflow_id, workflow_revision, workflow_fingerprint)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(task_key) DO UPDATE SET
                       close_at=excluded.close_at, target_status=excluded.target_status,
                       workflow_id=excluded.workflow_id,
                       workflow_revision=excluded.workflow_revision,
                       workflow_fingerprint=excluded.workflow_fingerprint,
                       state='pending', current_status=NULL, checked_at=NULL,
                       revision=scheduled_closures.revision + 1
                   WHERE scheduled_closures.close_at != excluded.close_at
                      OR scheduled_closures.target_status != excluded.target_status
                      OR scheduled_closures.workflow_fingerprint
                         IS NOT excluded.workflow_fingerprint
                      OR scheduled_closures.state IN ('cancelled', 'suspended')""",
                (
                    request.task_key,
                    request.close_at.timestamp(),
                    request.target_status,
                    request.workflow_id,
                    request.workflow_revision,
                    request.workflow_fingerprint,
                ),
            )
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM scheduled_closures WHERE task_key=?", (request.task_key,)
            ).fetchone()
            return self._decode(row)

    async def get(self, task_key: str) -> ScheduledClosure | None:
        return await asyncio.to_thread(self._get, task_key)

    def _get(self, task_key: str) -> ScheduledClosure | None:
        with closing(sqlite3.connect(self.path, timeout=10)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM scheduled_closures WHERE task_key=?", (task_key,)
            ).fetchone()
            return self._decode(row) if row else None

    async def due(self, now: datetime) -> list[ScheduledClosure]:
        return await asyncio.to_thread(self._due, now)

    def _due(self, now: datetime) -> list[ScheduledClosure]:
        with closing(sqlite3.connect(self.path, timeout=10)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """SELECT * FROM scheduled_closures
                   WHERE state='pending' AND close_at <= ? ORDER BY close_at""",
                (now.timestamp(),),
            ).fetchall()
            return [self._decode(row) for row in rows]

    async def save_context(
        self,
        request: ScheduledClosure,
        status: StatusReference | None,
        checked_at: datetime,
    ) -> bool:
        return await asyncio.to_thread(self._save_context, request, status, checked_at)

    def _save_context(
        self, request: ScheduledClosure, status: StatusReference | None, checked_at: datetime
    ) -> bool:
        with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
            cursor = connection.execute(
                """UPDATE scheduled_closures
                   SET state='context_ready', current_status=?, checked_at=?
                   WHERE task_key=? AND revision=? AND state='pending'""",
                (
                    status.model_dump_json() if status else None,
                    checked_at.timestamp(),
                    request.task_key,
                    request.revision,
                ),
            )
            return cursor.rowcount == 1

    @staticmethod
    def _decode(row: sqlite3.Row) -> ScheduledClosure:
        return ScheduledClosure(
            task_key=row["task_key"],
            revision=row["revision"],
            close_at=datetime.fromtimestamp(row["close_at"], UTC),
            target_status=row["target_status"],
            workflow_id=row["workflow_id"],
            workflow_revision=row["workflow_revision"],
            workflow_fingerprint=row["workflow_fingerprint"],
            state=row["state"],
            current_status=StatusReference.model_validate_json(row["current_status"])
            if row["current_status"]
            else None,
            checked_at=datetime.fromtimestamp(row["checked_at"], UTC)
            if row["checked_at"] is not None
            else None,
        )

    async def set_state(
        self, request: ScheduledClosure, state: str, status: StatusReference | None, now: datetime
    ) -> bool:
        return await asyncio.to_thread(self._set_state, request, state, status, now)

    def _set_state(
        self, request: ScheduledClosure, state: str, status: StatusReference | None, now: datetime
    ) -> bool:
        with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
            cursor = connection.execute(
                """UPDATE scheduled_closures SET state=?, current_status=?, checked_at=?,
                   revision=revision+1 WHERE task_key=? AND revision=?""",
                (
                    state,
                    status.model_dump_json() if status else None,
                    now.timestamp(),
                    request.task_key,
                    request.revision,
                ),
            )
            return cursor.rowcount == 1
