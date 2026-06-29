"""API key store backed by SQLite.

Keys let external apps inherit the orchestration engine. Only a SHA-256 hash is persisted; the
plaintext key is shown exactly once at creation. A fresh connection per operation keeps this
safe to call from the event loop and from worker threads. Swap SQLite for Postgres in a later
hardening pass — the `KeyStore` interface stays the same.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time
from dataclasses import dataclass

KEY_PREFIX = "cnx_"


@dataclass
class ApiKeyRecord:
    id: str
    name: str
    prefix: str  # first chars of the key, for display (not a secret)
    created_at: float
    revoked: bool
    request_count: int
    last_used_at: float | None
    # Cost metering (Initiative B). Accumulated across this key's runs.
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    # Optional spend cap in USD; None = unlimited. Requests are blocked (402) once cost_usd >= cap.
    spend_cap_usd: float | None = None

    @property
    def over_cap(self) -> bool:
        return self.spend_cap_usd is not None and self.cost_usd >= self.spend_cap_usd


def _hash(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class KeyStore:
    def __init__(self, path: str):
        self._path = path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_keys (
                    id            TEXT PRIMARY KEY,
                    name          TEXT NOT NULL,
                    key_hash      TEXT NOT NULL UNIQUE,
                    prefix        TEXT NOT NULL,
                    created_at    REAL NOT NULL,
                    revoked       INTEGER NOT NULL DEFAULT 0,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    last_used_at  REAL
                )
                """
            )
            # Lightweight migration: add metering columns to pre-existing tables.
            existing = {row["name"] for row in conn.execute("PRAGMA table_info(api_keys)")}
            for col, ddl in (
                ("input_tokens", "input_tokens INTEGER NOT NULL DEFAULT 0"),
                ("output_tokens", "output_tokens INTEGER NOT NULL DEFAULT 0"),
                ("cost_usd", "cost_usd REAL NOT NULL DEFAULT 0"),
                ("spend_cap_usd", "spend_cap_usd REAL"),
            ):
                if col not in existing:
                    conn.execute(f"ALTER TABLE api_keys ADD COLUMN {ddl}")

    def create(self, name: str) -> tuple[str, ApiKeyRecord]:
        """Generate a new key. Returns (plaintext_key, record). The plaintext is not stored."""
        raw = KEY_PREFIX + secrets.token_urlsafe(32)
        record = ApiKeyRecord(
            id=secrets.token_hex(8),
            name=name,
            prefix=raw[: len(KEY_PREFIX) + 8],
            created_at=time.time(),
            revoked=False,
            request_count=0,
            last_used_at=None,
        )
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO api_keys (id, name, key_hash, prefix, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (record.id, record.name, _hash(raw), record.prefix, record.created_at),
            )
        return raw, record

    def verify(self, raw_key: str) -> ApiKeyRecord | None:
        """Return the record for a valid, non-revoked key and meter the request; else None."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM api_keys WHERE key_hash = ? AND revoked = 0",
                (_hash(raw_key),),
            ).fetchone()
            if row is None:
                return None
            now = time.time()
            conn.execute(
                "UPDATE api_keys SET request_count = request_count + 1, last_used_at = ? "
                "WHERE id = ?",
                (now, row["id"]),
            )
            return _to_record(row, request_count=row["request_count"] + 1, last_used_at=now)

    def get(self, key_id: str) -> ApiKeyRecord | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,)).fetchone()
        return _to_record(row) if row else None

    def list(self) -> list[ApiKeyRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM api_keys ORDER BY created_at DESC"
            ).fetchall()
        return [_to_record(r) for r in rows]

    def add_usage(
        self, key_id: str, *, input_tokens: int, output_tokens: int, cost_usd: float
    ) -> None:
        """Accumulate a finished run's tokens/cost onto the key (audit + spend-cap basis)."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE api_keys SET input_tokens = input_tokens + ?, "
                "output_tokens = output_tokens + ?, cost_usd = round(cost_usd + ?, 6) "
                "WHERE id = ?",
                (int(input_tokens), int(output_tokens), float(cost_usd), key_id),
            )

    def set_spend_cap(self, key_id: str, cap_usd: float | None) -> bool:
        """Set (or clear, with None) the per-key USD spend cap."""
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE api_keys SET spend_cap_usd = ? WHERE id = ?", (cap_usd, key_id)
            )
            return cur.rowcount > 0

    def revoke(self, key_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE api_keys SET revoked = 1 WHERE id = ? AND revoked = 0", (key_id,)
            )
            return cur.rowcount > 0


def _to_record(row: sqlite3.Row, **overrides) -> ApiKeyRecord:
    keys = row.keys()
    return ApiKeyRecord(
        id=row["id"],
        name=row["name"],
        prefix=row["prefix"],
        created_at=row["created_at"],
        revoked=bool(row["revoked"]),
        request_count=overrides.get("request_count", row["request_count"]),
        last_used_at=overrides.get("last_used_at", row["last_used_at"]),
        input_tokens=row["input_tokens"] if "input_tokens" in keys else 0,
        output_tokens=row["output_tokens"] if "output_tokens" in keys else 0,
        cost_usd=row["cost_usd"] if "cost_usd" in keys else 0.0,
        spend_cap_usd=row["spend_cap_usd"] if "spend_cap_usd" in keys else None,
    )
