"""Regression: /api/runs returned HTTP 500 once Jev smoke/pilot folders (manifest without started_at) existed."""

import hashlib
import json

from fastapi.testclient import TestClient

import deepsift.api.app as api


def _write(d, name, obj):
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(obj))


def _digest(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


def test_runs_endpoint_skips_non_study_folders(tmp_path, monkeypatch):
    runs, figs = tmp_path / "runs", tmp_path / "figures"
    figs.mkdir()
    # 1. valid study run
    _write(runs / "20260924T204836-test-c6f9", "manifest.json",
           {"run_id": "20260924T204836-test-c6f9", "split": "test", "started_at": "2026-09-24T20:48:36+00:00",
            "config_version": "d59227d52476", "engines": [{"key": "MOCK"}]})
    _write(runs / "20260924T204836-test-c6f9", "results.json", {})
    # 2. Jev smoke/pilot folder: its own manifest schema, no started_at, no results.json
    _write(runs / "20260925T090119-jev-smoke-b935", "manifest.json",
           {"run_id": "20260925T090119-jev-smoke-b935", "split": "validation", "mode": "smoke", "config_version": "x"})
    _write(runs / "20260925T090044-jev-probe-6ded", "probe.json", {"passed": True})          # no manifest at all
    # a genuinely malformed study run is skipped too, but reported
    _write(runs / "20260101T000000-validation-bad0", "manifest.json", {"run_id": "20260101T000000-validation-bad0", "split": "validation"})
    _write(runs / "20260101T000000-validation-bad0", "results.json", {})
    before = _digest(tmp_path)
    monkeypatch.setattr(api, "RUNS_ROOT", runs)
    monkeypatch.setattr(api, "FIG_ROOT", figs)

    r = TestClient(api.app).get("/api/runs")                          # no `with`: the pipeline boot is not triggered

    assert r.status_code == 200
    ids = [x["run_id"] for x in r.json()]
    assert ids == ["20260924T204836-test-c6f9"]
    assert r.json()[0]["started_at"] == "2026-09-24T20:48:36+00:00" and r.json()[0]["engines"] == ["MOCK"]
    kinds = {s["run_id"]: s["kind"] for s in api.LAST_RUNS_SKIPPED}
    assert kinds == {"20260925T090119-jev-smoke-b935": "not_a_study_run", "20260101T000000-validation-bad0": "malformed_study_run"}
    assert r.headers["X-DEEPSIFT-Skipped-Runs"] == "2" and r.headers["X-DEEPSIFT-Malformed-Study-Runs"] == "1"
    assert _digest(tmp_path) == before                                # nothing on disk was touched
