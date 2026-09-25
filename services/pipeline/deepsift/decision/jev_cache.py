"""Persistent Jev inference cache (SQLite, data/processed/jev_cache.sqlite — git-ignored).

Key = sha256 of the canonical JSON of
    { state (exact payload, which already contains the objective for variants that include it),
      questions (exact question schema), variant, model_requested, sdk_version }
so an identical request is never sent twice. Changing budget, storage, priority weights or the
objective's *weights* never changes a key; changing the objective *text* changes keys only for the
variant that puts the objective in Jev's context (FULL_CONTEXT).

Note: TypeSafe's own cookbook measures run-to-run variation of answers; a cache hit therefore reuses
one recorded draw. Repeat-variability is measured separately (scripts/jev_pilot.py --repeat).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from deepsift.core.config import DATA_DIR

CACHE_PATH = DATA_DIR / "processed" / "jev_cache.sqlite"
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS jev_cache (
  input_hash TEXT PRIMARY KEY, event_id TEXT, variant TEXT, model_requested TEXT, model_returned TEXT,
  sdk_version TEXT, request_id TEXT, questions_json TEXT, state_json TEXT, answers_json TEXT,
  latency_ms REAL, input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL, created_at TEXT, run_id TEXT
);
"""


def request_key(state: dict, questions: dict, variant: str, model: str, sdk_version: str) -> str:
    blob = json.dumps({"state": state, "questions": questions, "variant": variant, "model": model, "sdk": sdk_version},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


class JevCache:
    def __init__(self, path: Path | None = None):
        self.path = path or CACHE_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self):
        return sqlite3.connect(self.path, timeout=30)

    def get(self, key: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT model_returned, request_id, answers_json, latency_ms, input_tokens, output_tokens, cost_usd, "
                            "created_at, run_id FROM jev_cache WHERE input_hash=?", [key]).fetchone()
        if not row:
            return None
        return {"model_returned": row[0], "request_id": row[1], "answers": json.loads(row[2]), "latency_ms": row[3],
                "input_tokens": row[4], "output_tokens": row[5], "cost_usd": row[6], "created_at": row[7], "run_id": row[8]}

    def has(self, key: str) -> bool:
        with self._conn() as c:
            return c.execute("SELECT 1 FROM jev_cache WHERE input_hash=?", [key]).fetchone() is not None

    def keys(self) -> set[str]:
        with self._conn() as c:
            return {r[0] for r in c.execute("SELECT input_hash FROM jev_cache")}

    def put(self, key: str, *, event_id, variant, model_requested, model_returned, sdk_version, request_id, questions,
            state, answers, latency_ms, input_tokens, output_tokens, cost_usd, run_id) -> None:
        with _lock, self._conn() as c:
            c.execute("INSERT OR IGNORE INTO jev_cache VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
                key, event_id, variant, model_requested, model_returned, sdk_version, request_id,
                json.dumps(questions, ensure_ascii=False), json.dumps(state, ensure_ascii=False), json.dumps(answers),
                latency_ms, input_tokens, output_tokens, cost_usd, datetime.now(timezone.utc).isoformat(), run_id])

    def stats(self) -> dict:
        with self._conn() as c:
            n, tok, cost = c.execute("SELECT COUNT(*), COALESCE(SUM(input_tokens),0), COALESCE(SUM(cost_usd),0) FROM jev_cache").fetchone()
            chars = c.execute("SELECT COALESCE(SUM(LENGTH(state_json)+LENGTH(questions_json)),0) FROM jev_cache WHERE input_tokens IS NOT NULL").fetchone()[0]
            lat = [r[0] for r in c.execute("SELECT latency_ms FROM jev_cache WHERE latency_ms IS NOT NULL")]
        lat.sort()
        return {"entries": n, "input_tokens": tok, "cost_usd": cost,
                "measured_chars_per_token": (chars / tok) if tok else None,
                "latency_p50_ms": lat[len(lat) // 2] if lat else None}
