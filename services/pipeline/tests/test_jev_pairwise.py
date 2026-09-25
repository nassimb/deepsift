"""JEV PAIRWISE REVIEWER: text-only state, no strategy leakage, order-aware versioned cache key — SYNTHETIC TEST DATA."""

import pytest

from deepsift.decision import jev_pairwise as P


def _obs(sol=412, pose=(17, 826, 2), seq="trav00108"):
    return {"stereo": True, "primary_tier": "D", "sequence_id": seq, "sol": sol, "utc": "2013-10-03T11:04:39.557", "scene_cluster": 0,
            "source_metadata": {"pose": list(pose)},
            "image_features": {"brightness": 0.4, "contrast": 0.07, "entropy_bits": 6.1, "sharpness": 0.01, "saturated_fraction": 0.0,
                               "missing_fraction": 0.0, "embedding_novelty": 0.5},
            "telemetry_context": {"context_events": ["E1"], "telemetry_score": 0.7}}


def test_state_is_text_only_and_clean():
    oa, ob = _obs(), _obs(pose=(17, 826, 3))
    s = P.pair_state(P.side_summary(oa, 150.0, 0.1, "passed", 1), P.side_summary(ob, 160.0, None, "passed", 2),
                     P.relation(oa, ob, 3.0, 0.2, 20))
    P.assert_clean(s)
    text = str(s).lower()
    for bad in ("rank", "score", "novelty", "http", "image_url", "caption", "msl-nav"):
        assert bad not in text
    assert "no image is provided" in text


def test_assert_clean_rejects_leakage():
    for leak in ({"size_rank": 1}, {"x": "strategy FIFO"}, {"telemetry_score": 0.5}, {"image_url": "/x"}, {"y": "https://pds"}):
        with pytest.raises(ValueError):
            P.assert_clean({"observation_A": leak})


def test_cache_key_depends_on_order_snapshot_transport_and_schema():
    s = {"a": 1}
    k = P.request_key(s, "AB", "typesafe/jev-1.13", P.EXPECTED_SNAPSHOT, "0.7.1", "openrouter")
    assert k != P.request_key(s, "BA", "typesafe/jev-1.13", P.EXPECTED_SNAPSHOT, "0.7.1", "openrouter")
    assert k != P.request_key(s, "AB", "typesafe/jev-1.13", "typesafe/jev-1.13-other", "0.7.1", "openrouter")
    assert k != P.request_key(s, "AB", "typesafe/jev-1.13", P.EXPECTED_SNAPSHOT, "0.7.1", "direct")
    assert k != P.request_key({"a": 2}, "AB", "typesafe/jev-1.13", P.EXPECTED_SNAPSHOT, "0.7.1", "openrouter")


def test_cache_rejects_other_snapshot(tmp_path):
    c = P.PairwiseCache(tmp_path / "c.sqlite")
    c.put("k", pair_id="P0", order="AB", model_requested="m", model_returned="typesafe/jev-1.13-OLD", transport="openrouter",
          provider="TypeSafe", answers={}, latency_ms=1.0, input_tokens=1, output_tokens=1, cost_usd=0.0, run_id="r")
    assert c.get("k", P.EXPECTED_SNAPSHOT) is None and c.get("k", "typesafe/jev-1.13-OLD") is not None


def test_question_text_is_exact():
    assert P.QUESTIONS["priority"].instructions == ("If only one of these two observations could be downlinked at useful image quality, "
                                                    "which should be prioritized to preserve useful mission coverage under bandwidth constraints?")
    assert set(P.QUESTIONS["priority"].criteria) == {"A", "B", "EQUAL", "UNSURE"}
    assert set(P.QUESTIONS["reason"].criteria) == {"SPATIAL_COVERAGE", "VISUAL_CHANGE", "IMAGE_QUALITY", "BANDWIDTH_EFFICIENCY",
                                                   "STEREO_VALUE", "NO_CLEAR_ADVANTAGE"}
