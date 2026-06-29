"""Background run model with SQLite persistence (audit trail).

`POST /v1/orchestrate` runs synchronously and returns the full result. For the live "God View"
workflow, `POST /v1/runs` starts a run in the background, returns a `run_id` immediately, and the
client watches progress over the telemetry WebSocket, then fetches the result with
`GET /v1/runs/{run_id}`.

Runs are persisted to SQLite so they survive a restart and form an audit trail. A fresh
connection per operation keeps this safe to call from the event loop and from worker threads.
Swap SQLite for Postgres in a future scaling pass — the `RunRegistry` interface stays the same.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from typing import Any

from app.orchestrator.graph import run_orchestration
from app.telemetry.events import OrchestratorEvent, Phase


@dataclass
class RunRecord:
    run_id: str
    query: str
    status: str = "pending"  # pending | running | done | max_iterations | error
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float | None = None
    updated_at: float | None = None


class RunRegistry:
    def __init__(self, db_path: str):
        self._db = db_path
        self._tasks: set = set()  # strong refs so background tasks aren't GC'd mid-run
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id      TEXT PRIMARY KEY,
                    query       TEXT NOT NULL,
                    status      TEXT NOT NULL,
                    result_json TEXT,
                    error       TEXT,
                    created_at  REAL NOT NULL,
                    updated_at  REAL NOT NULL
                )
                """
            )

    def create(self, query: str) -> RunRecord:
        now = time.time()
        record = RunRecord(
            run_id=uuid.uuid4().hex, query=query, status="pending",
            created_at=now, updated_at=now,
        )
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO runs (run_id, query, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (record.run_id, record.query, record.status, now, now),
            )
        return record

    def get(self, run_id: str) -> RunRecord | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return RunRecord(
            run_id=row["run_id"],
            query=row["query"],
            status=row["status"],
            result=json.loads(row["result_json"]) if row["result_json"] else None,
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def set_status(self, run_id: str, status: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ?",
                (status, time.time(), run_id),
            )

    def finish(self, run_id: str, status: str, result: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE runs SET status = ?, result_json = ?, updated_at = ? WHERE run_id = ?",
                (status, json.dumps(result), time.time(), run_id),
            )

    def fail(self, run_id: str, error: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE runs SET status = 'error', error = ?, updated_at = ? WHERE run_id = ?",
                (error, time.time(), run_id),
            )

    def track(self, task) -> None:
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


def final_to_result(final: dict) -> dict[str, Any]:
    """Normalize a final graph state into the public result shape (matches OrchestrateResponse)."""
    return {
        "run_id": final["run_id"],
        "status": final["status"],
        "answer": final["answer"],
        "iterations": final["iterations"],
        "steps": final["steps"],
        "usage": final.get("usage", {}),
    }


async def start_background_run(
    app, query: str, context: str | None = None, *, max_iterations: int | None = None,
    key_id: str | None = None,
) -> str:
    """Kick off an orchestration run in the background and return its run_id immediately."""
    registry: RunRegistry = app.state.runs
    bus = app.state.bus
    record = registry.create(query)
    registry.set_status(record.run_id, "running")

    async def _run() -> None:
        try:
            final = await asyncio.to_thread(
                run_orchestration,
                app.state.orchestrator,
                query,
                context,
                max_iterations=max_iterations,
                run_id=record.run_id,
            )
            result = final_to_result(final)
            registry.finish(record.run_id, final["status"], result)
            # Meter the finished run's tokens/cost against the key that started it.
            if key_id and getattr(app.state, "keys", None) is not None:
                usage = result.get("usage") or {}
                app.state.keys.add_usage(
                    key_id,
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                    cost_usd=usage.get("cost_usd", 0.0),
                )
        except Exception as exc:  # noqa: BLE001 — surface any failure to watchers
            registry.fail(record.run_id, str(exc))
            bus.publish(
                OrchestratorEvent(run_id=record.run_id, phase=Phase.ERROR, message=str(exc))
            )

    registry.track(asyncio.create_task(_run()))
    return record.run_id
