"""Audit log (DuckDB). Every decision is stored with the exact inputs needed to reproduce it."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from deepsift.core.config import DATA_DIR, PIPELINE_VERSION, Config, diff

DB_PATH = DATA_DIR / "processed" / "audit.duckdb"
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id VARCHAR PRIMARY KEY, created_at TIMESTAMP, pipeline_version VARCHAR, config_version VARCHAR,
    engine VARCHAR, deep_provider VARCHAR, objective_id VARCHAR, data_source VARCHAR, sols VARCHAR,
    n_events INTEGER, timings_json VARCHAR, note VARCHAR
);
CREATE TABLE IF NOT EXISTS decisions (
    run_id VARCHAR, event_id VARCHAR, recorded_at TIMESTAMP, pipeline_version VARCHAR,
    engine VARCHAR, model VARCHAR, decision_json VARCHAR, deep_json VARCHAR, confidence DOUBLE, gate VARCHAR,
    objective_id VARCHAR, objective_json VARCHAR, config_version VARCHAR, event_json VARCHAR,
    priority_json VARCHAR, proposed_action VARCHAR, final_action VARCHAR, explanation_json VARCHAR
);
CREATE TABLE IF NOT EXISTS config_versions (version VARCHAR PRIMARY KEY, created_at TIMESTAMP, config_json VARCHAR);
CREATE TABLE IF NOT EXISTS config_changes (
    changed_at TIMESTAMP, from_version VARCHAR, to_version VARCHAR, diff_json VARCHAR, actor VARCHAR, note VARCHAR
);
CREATE TABLE IF NOT EXISTS labels (
    label_id VARCHAR PRIMARY KEY, created_at TIMESTAMP, source VARCHAR, event_id VARCHAR, t_start VARCHAR, t_end VARCHAR,
    instrument VARCHAR, expected_type VARCHAR, severity VARCHAR, note VARCHAR, author VARCHAR
);
"""


class AuditLog:
    def __init__(self, path: Path | None = None):
        self.path = path or DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute(SCHEMA)

    def _conn(self):
        return duckdb.connect(str(self.path))

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def record_config(self, cfg: Config) -> str:
        v = cfg.version()
        with _lock, self._conn() as c:
            if not c.execute("SELECT 1 FROM config_versions WHERE version = ?", [v]).fetchone():
                c.execute("INSERT INTO config_versions VALUES (?, ?, ?)", [v, self._now(), json.dumps(cfg.model_dump(mode="json"))])
        return v

    def get_config(self, version: str) -> Config | None:
        with self._conn() as c:
            row = c.execute("SELECT config_json FROM config_versions WHERE version = ?", [version]).fetchone()
        return Config.model_validate(json.loads(row[0])) if row else None

    def record_config_change(self, before: Config, after: Config, actor: str = "ui", note: str = "") -> list[dict]:
        self.record_config(before)
        self.record_config(after)
        changes = diff(before.model_dump(mode="json"), after.model_dump(mode="json"))
        with _lock, self._conn() as c:
            c.execute("INSERT INTO config_changes VALUES (?, ?, ?, ?, ?, ?)",
                      [self._now(), before.version(), after.version(), json.dumps(changes), actor, note])
        return changes

    def config_changes(self, limit: int = 200) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT changed_at, from_version, to_version, diff_json, actor, note FROM config_changes "
                             "ORDER BY changed_at DESC LIMIT ?", [limit]).fetchall()
        return [{"changed_at": r[0].isoformat() + "Z", "from_version": r[1], "to_version": r[2],
                 "diff": json.loads(r[3]), "actor": r[4], "note": r[5]} for r in rows]

    def record_run(self, run_id: str, cfg: Config, engine: str, deep: str, objective_id: str, data_source: str,
                   sols: list[int], n_events: int, timings: dict, note: str = "") -> None:
        with _lock, self._conn() as c:
            c.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
                run_id, self._now(), PIPELINE_VERSION, cfg.version(), engine, deep, objective_id, data_source,
                json.dumps(sols), n_events, json.dumps(timings), note])

    def record_decisions(self, run_id: str, events, objective, cfg: Config) -> None:
        now = self._now()
        rows = []
        for e in events:
            d = e.decision
            rows.append([
                run_id, e.id, now, PIPELINE_VERSION, d.engine if d else None, d.model if d else None,
                d.model_dump_json(exclude={"state_sent"}) if d else None, e.deep.model_dump_json() if e.deep else None,
                e.priority.confidence if e.priority else None, e.gate.value if e.gate else None,
                objective.id, objective.model_dump_json(), cfg.version(),
                e.model_dump_json(exclude={"decision": {"state_sent"}, "trace": True}),
                e.priority.model_dump_json() if e.priority else None,
                e.proposed_action.value if e.proposed_action else None, e.final_action.value if e.final_action else None,
                json.dumps(e.explanation),
            ])
        with _lock, self._conn() as c:
            c.executemany("INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)

    def decisions(self, event_id: str | None = None, run_id: str | None = None, limit: int = 500) -> list[dict]:
        q = ("SELECT run_id, event_id, recorded_at, pipeline_version, engine, model, confidence, gate, objective_id, "
             "config_version, proposed_action, final_action FROM decisions WHERE 1=1")
        args: list = []
        if event_id:
            q += " AND event_id = ?"
            args.append(event_id)
        if run_id:
            q += " AND run_id = ?"
            args.append(run_id)
        q += " ORDER BY recorded_at DESC LIMIT ?"
        args.append(limit)
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        keys = ["run_id", "event_id", "recorded_at", "pipeline_version", "engine", "model", "confidence", "gate",
                "objective_id", "config_version", "proposed_action", "final_action"]
        out = [dict(zip(keys, r)) for r in rows]
        for r in out:
            r["recorded_at"] = r["recorded_at"].isoformat() + "Z"
        return out

    def decision_record(self, run_id: str, event_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT decision_json, deep_json, gate, objective_json, config_version, event_json, "
                            "priority_json, proposed_action, final_action FROM decisions WHERE run_id=? AND event_id=? "
                            "ORDER BY recorded_at DESC LIMIT 1", [run_id, event_id]).fetchone()
        if not row:
            return None
        return {"decision": json.loads(row[0]) if row[0] else None, "deep": json.loads(row[1]) if row[1] else None,
                "gate": row[2], "objective": json.loads(row[3]), "config_version": row[4],
                "event": json.loads(row[5]), "priority": json.loads(row[6]) if row[6] else None,
                "proposed_action": row[7], "final_action": row[8]}

    def runs(self, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT run_id, created_at, pipeline_version, config_version, engine, deep_provider, objective_id, "
                             "data_source, sols, n_events, timings_json, note FROM runs ORDER BY created_at DESC LIMIT ?", [limit]).fetchall()
        keys = ["run_id", "created_at", "pipeline_version", "config_version", "engine", "deep_provider", "objective_id",
                "data_source", "sols", "n_events", "timings", "note"]
        out = []
        for r in rows:
            d = dict(zip(keys, r))
            d["created_at"] = d["created_at"].isoformat() + "Z"
            d["sols"] = json.loads(d["sols"])
            d["timings"] = json.loads(d["timings"])
            out.append(d)
        return out

    def add_label(self, label: dict) -> None:
        with _lock, self._conn() as c:
            c.execute("INSERT OR REPLACE INTO labels VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
                label["label_id"], self._now(), label["source"], label.get("event_id"), label["t_start"], label["t_end"],
                label.get("instrument"), label.get("expected_type"), label.get("severity", "medium"), label.get("note", ""),
                label.get("author", "anonymous")])

    def labels(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT label_id, created_at, source, event_id, t_start, t_end, instrument, expected_type, "
                             "severity, note, author FROM labels ORDER BY created_at").fetchall()
        keys = ["label_id", "created_at", "source", "event_id", "t_start", "t_end", "instrument", "expected_type", "severity", "note", "author"]
        out = [dict(zip(keys, r)) for r in rows]
        for r in out:
            r["created_at"] = r["created_at"].isoformat() + "Z"
        return out
