"""Phase 3.1 review API: blinding (no scores before the answer), storage, validation — SYNTHETIC TEST DATA."""

import json

from fastapi.testclient import TestClient

import deepsift.api.app as api


def test_review_is_blind_until_answered(tmp_path, monkeypatch):
    pairs = {"version": "T", "question": "Which observation would you prioritize for downlink?", "pairs": [
        {"pair_id": "P0", "A": "X1", "B": "X2", "category": "SIZE_VS_NOVELTY", "scores": {"X1": {"novelty_rank": 1}, "X2": {"novelty_rank": 9}}}]}
    (tmp_path / "pairs_v1.json").write_text(json.dumps(pairs))
    monkeypatch.setattr(api, "REVIEW_DIR", tmp_path)
    monkeypatch.setattr(api, "REVIEW_PAIRS", tmp_path / "pairs_v1.json")
    monkeypatch.setattr(api, "REVIEW_ANN", tmp_path / "annotations_v1.jsonl")
    monkeypatch.setattr(api, "_review_acq", {k: {"sol": 412, "utc": "2013-10-03T11:04:39", "sequence_id": "trav00108", "primary_tier": "D",
                                                 "stereo": True} for k in ("X1", "X2")})
    c = TestClient(api.app)
    nxt = c.get("/api/review/next").json()
    text = json.dumps(nxt)
    assert nxt["pair_id"] == "P0" and "scores" not in text and "category" not in text and "novelty" not in text
    assert nxt["A"]["label"] == "NASA PDS OBSERVATION"
    assert c.post("/api/review/annotations", json={"pair_id": "P0", "choice": "MAYBE"}).status_code == 422
    r = c.post("/api/review/annotations", json={"pair_id": "P0", "choice": "B", "note": "sharper"}).json()
    assert r["revealed"]["category"] == "SIZE_VS_NOVELTY" and r["annotation"]["choice"] == "B"
    stored = [json.loads(x) for x in (tmp_path / "annotations_v1.jsonl").read_text().splitlines()]
    assert stored[0]["A"] == "X1" and stored[0]["timestamp"] and stored[0]["annotation_id"]
    assert c.get("/api/review/next").json()["done"] is True
