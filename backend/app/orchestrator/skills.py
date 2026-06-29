"""Reusable skills — a persistent, agent-built toolbox (Initiative D).

When the orchestrator writes Python that works, it can **save it as a named skill**. On later runs
it sees a compact catalog (names + descriptions only — *progressive disclosure*, the code-mode
token win) and can `load_skill(name)` to pull the full code on demand, instead of re-deriving it.

Skills are persisted to SQLite so the toolbox survives restarts. A fresh connection per operation
keeps this safe to call from the event loop and from worker threads.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass, field

# Skill names are referenced by the model and in URLs — keep them simple and safe.
_NAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")


class InvalidSkillName(ValueError):
    pass


@dataclass
class Skill:
    name: str
    description: str
    code: str
    tags: list[str] = field(default_factory=list)
    created_at: float | None = None
    updated_at: float | None = None
    use_count: int = 0
    last_used_at: float | None = None

    def catalog_line(self) -> str:
        """Compact one-liner for the system-prompt catalog (no code — progressive disclosure)."""
        tagstr = f" [{', '.join(self.tags)}]" if self.tags else ""
        return f"- {self.name}: {self.description}{tagstr}"


def validate_name(name: str) -> str:
    name = (name or "").strip()
    if not _NAME_RE.match(name):
        raise InvalidSkillName(
            "Skill name must be 1–64 chars of letters, digits, '_', '.', or '-'."
        )
    return name


class SkillStore:
    def __init__(self, db_path: str):
        self._db = db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skills (
                    name         TEXT PRIMARY KEY,
                    description  TEXT NOT NULL,
                    code         TEXT NOT NULL,
                    tags_json    TEXT NOT NULL DEFAULT '[]',
                    created_at   REAL NOT NULL,
                    updated_at   REAL NOT NULL,
                    use_count    INTEGER NOT NULL DEFAULT 0,
                    last_used_at REAL
                )
                """
            )

    def save(self, name: str, description: str, code: str, tags: list[str] | None = None) -> Skill:
        """Create or update a skill (upsert by name). Returns the stored skill."""
        name = validate_name(name)
        if not description or not code:
            raise ValueError("A skill needs both a description and code.")
        now = time.time()
        tags = tags or []
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT created_at FROM skills WHERE name = ?", (name,)
            ).fetchone()
            created = existing["created_at"] if existing else now
            conn.execute(
                "INSERT INTO skills (name, description, code, tags_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET description=excluded.description, "
                "code=excluded.code, tags_json=excluded.tags_json, updated_at=excluded.updated_at",
                (name, description, code, json.dumps(tags), created, now),
            )
        return Skill(name=name, description=description, code=code, tags=tags,
                     created_at=created, updated_at=now)

    def get(self, name: str) -> Skill | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM skills WHERE name = ?", (name,)).fetchone()
        return _to_skill(row) if row else None

    def list(self) -> list[Skill]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM skills ORDER BY use_count DESC, updated_at DESC"
            ).fetchall()
        return [_to_skill(r) for r in rows]

    def search(self, query: str) -> list[Skill]:
        q = (query or "").strip().lower()
        if not q:
            return self.list()
        return [
            s for s in self.list()
            if q in s.name.lower() or q in s.description.lower()
            or any(q in t.lower() for t in s.tags)
        ]

    def record_use(self, name: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE skills SET use_count = use_count + 1, last_used_at = ? WHERE name = ?",
                (time.time(), name),
            )

    def delete(self, name: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM skills WHERE name = ?", (name,))
            return cur.rowcount > 0

    def catalog(self, limit: int = 50) -> str:
        """Compact catalog (names + descriptions) for the system prompt. Empty string if none."""
        skills = self.list()[:limit]
        if not skills:
            return ""
        return "\n".join(s.catalog_line() for s in skills)


def _to_skill(row: sqlite3.Row) -> Skill:
    return Skill(
        name=row["name"],
        description=row["description"],
        code=row["code"],
        tags=json.loads(row["tags_json"]) if row["tags_json"] else [],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        use_count=row["use_count"],
        last_used_at=row["last_used_at"],
    )
