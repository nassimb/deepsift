"""Phase 3.4 simplified primary path: pHash, QUALITY_V2, telemetry and Jev cannot change any primary decision.
SYNTHETIC TEST DATA."""

import copy
import random

import numpy as np
import pytest

from deepsift.evaluation import phase3_pipeline as P
from deepsift.evaluation import traverse as T


def _obs(n=40, seed=0):
    r = random.Random(seed)
    out = []
    for i in range(n):
        out.append({"id": f"X{i:03d}", "utc": f"2015-01-01T00:{i:02d}:00", "stereo": True,
                    "downlink": {"full_bytes": r.uniform(1e4, 1e6)},
                    "image_features": {"embedding_novelty": r.random(), "sharpness": r.random()},
                    "quality_state": "CLEAN", "near_duplicate_group": i, "telemetry_context": {"telemetry_score": 0.0}})
    return out


def test_primary_orders_ignore_diagnostic_signals():
    obs = _obs()
    base = P.primary_orders(obs)
    noisy = copy.deepcopy(obs)
    r = random.Random(1)
    for o in noisy:
        o["quality_state"] = r.choice(["CLEAN", "SUSPECT", "DEGRADED"])
        o["near_duplicate_group"] = r.randrange(3)                    # aggressive pHash merging
        o["telemetry_context"]["telemetry_score"] = r.random()
        o["jev"] = {"choice": r.choice("AB")}
    assert P.primary_orders(noisy) == base
    assert set(base) == set(P.PRIMARY_GLOBAL_ORDERS)


def test_traverse_selection_uses_positions_and_embeddings_only():
    rng = np.random.default_rng(0)
    xy = np.cumsum(rng.uniform(0, 3, size=(30, 2)), axis=0)
    emb = rng.normal(size=(30, 16))
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)
    for m in P.PRIMARY_TRAVERSE_METHODS + P.BASELINE_TRAVERSE_METHODS:
        for f in (0.5, 0.25, 0.125):
            s = P.select_traverse(m, xy, emb, f)
            assert len(s) == int(np.ceil(f * 30)) and s == sorted(set(s))
    with pytest.raises(ValueError):
        P.select_traverse("PHASH_REPRESENTATIVES", xy, emb, 0.25)


def test_quality_is_diagnostic_flag_only():
    f = P.quality_flag(("SUSPECT", ["low_sharpness"]))
    assert f["flag"] == P.QUALITY_SUSPECT and "does not affect" in f["role"]
    assert P.quality_flag(("CLEAN", []))["flag"] == P.QUALITY_NOT_FLAGGED


def test_distance_to_kept_is_zero_for_send_all_and_density_invariant():
    xy = np.array([[0, 0], [0, 0], [0, 0], [20, 0], [20, 0], [40, 0]], float)
    emb = np.eye(6)
    m = T.metrics(xy, emb, list(range(6)))
    assert m["max_distance_to_kept_m"] == 0.0
    dense = np.array([[x, 0] for x in np.arange(0, 40.5, 0.5)], float)
    md = T.metrics(dense, np.eye(len(dense)), list(range(len(dense))))
    assert md["max_distance_to_kept_m"] == 0.0 and md["max_gap_m"] == pytest.approx(0.5)
