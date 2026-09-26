"""v1 research release: every public headline number equals the frozen final-test artifact (no hand-typed numbers)."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FINAL = ROOT / "artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json"
REL = ROOT / "apps/web/data/release.json"


def test_release_headline_matches_frozen_final_test():
    f = json.loads(FINAL.read_text())
    r = json.loads(REL.read_text())
    assert r["headline"]["result"] == f["primary"]["RESULT"] == "PASS"
    for k, v in f["primary"]["metrics"].items():
        assert r["headline"][k] == v
    assert r["final_summary"] == f["traverse"]["summary"]
    assert r["secondary"]["CONCLUSION"] == f["secondary_embedding"]["CONCLUSION"]
    for p in r["periods"]:
        label = next(k for k in f["four_period"] if k.split()[0].lower().replace("validation", "validation") in p["label"].lower())
        assert p["position"]["coverage_5m"] == f["four_period"][label]["POSITION"]["coverage_5m"]
        assert p["embedding_gain"] == f["four_period"][label]["embedding_gain"]
    assert r["reproducibility"]["frozen_before_download"]["config_before_download"] is True
