"""SCHEDULER_V2_PROGRESSIVE monotonicity (property test on random SYNTHETIC cost tables)."""

import random

from deepsift.evaluation.image_benchmark import RANK, allocate, allocate_progressive


def _costs(rng, n):
    out = []
    for _ in range(n):
        meta = rng.uniform(150, 300)
        thumb = rng.uniform(400, 700)
        comp = rng.uniform(2_000, 60_000) if rng.random() > 0.05 else None
        out.append({"NONE": 0.0, "METADATA": meta, "THUMBNAIL": thumb, "COMPRESSED": comp, "FULL": rng.uniform(60_000, 800_000)})
    return out


def _represented(tiers, clusters):
    idx = [i for i, t in enumerate(tiers) if RANK[t] >= RANK["THUMBNAIL"]]
    return len(idx), len({clusters[i] for i in idx}), sum(1 for t in tiers if t != "NONE")


def test_v2_coverage_is_monotone_in_budget():
    rng = random.Random(7)
    for trial in range(200):
        n = rng.randint(5, 60)
        costs = _costs(rng, n)
        clusters = [rng.randint(0, n // 2) for _ in range(n)]
        order = list(range(n))
        rng.shuffle(order)
        total = sum(c["FULL"] for c in costs)
        prev = (0, 0, 0)
        for f in sorted(rng.uniform(0, 0.3) for _ in range(25)) + [1.0, 2.0]:
            cur = _represented(allocate_progressive(costs, order, f * total), clusters)
            assert all(c >= p for c, p in zip(cur, prev)), (trial, f, prev, cur)
            prev = cur


def test_v2_never_skips_ahead_and_fills_cheap_tiers_first():
    costs = [{"NONE": 0, "METADATA": 100, "THUMBNAIL": 500, "COMPRESSED": 5_000, "FULL": 100_000} for _ in range(3)]
    assert allocate_progressive(costs, [0, 1, 2], 1_400) == ["THUMBNAIL", "THUMBNAIL", "METADATA"]
    assert allocate_progressive(costs, [0, 1, 2], 1_500 + 4_500) == ["COMPRESSED", "THUMBNAIL", "THUMBNAIL"]


def test_v1_greedy_can_be_non_monotone_documented_artifact():
    costs = [{"NONE": 0, "METADATA": 100, "THUMBNAIL": 500, "COMPRESSED": 5_000, "FULL": 100_000} for _ in range(10)]
    full_first = [[(i, "FULL") for i in range(10)]]
    usable = lambda b: sum(RANK[t] >= RANK["COMPRESSED"] for t in allocate(costs, full_first, b))  # noqa: E731
    assert usable(60_000) > usable(110_000)            # the V1 artifact V2 fixes


def test_v3_stereo_safe_monotone_and_never_one_eye_usable():
    from deepsift.evaluation.image_benchmark import cost_table_v3, coverage

    rng = random.Random(3)
    for trial in range(150):
        n = rng.randint(5, 50)
        eye = []
        obs = []
        for i in range(n):
            stereo = rng.random() < 0.8
            e = {"metadata": rng.uniform(150, 300), "stereo": stereo}
            for k in (["L", "R"] if stereo else ["L"]):
                e[k] = {"thumbnail": rng.uniform(400, 600), "compressed": rng.uniform(3_000, 40_000), "full": rng.uniform(60_000, 400_000)}
            eye.append(e)
            obs.append({"stereo": stereo, "scene_cluster": rng.randint(0, n // 2), "source_metadata": {"pose": [1, rng.randint(0, n // 3), 0]}})
        costs = cost_table_v3(eye)
        for i, e in enumerate(eye):                       # a stereo tier always costs both eyes
            if e["stereo"]:
                assert costs[i]["COMPRESSED"] == e["L"]["compressed"] + e["R"]["compressed"]
        order = list(range(n))
        rng.shuffle(order)
        total = sum(c["FULL"] for c in costs)
        keys = ["acquisitions_represented", "scene_clusters_represented", "rover_positions_represented", "stereo_pair_present", "stereo_pair_usable"]
        prev = None
        for f in sorted(rng.uniform(0, 0.4) for _ in range(40)) + [1.0, 3.0]:
            cov = coverage(obs, costs, allocate_progressive(costs, order, f * total), pair_semantics=True)
            cur = [cov[k] for k in keys]
            assert prev is None or all(c >= p for c, p in zip(cur, prev)), (trial, f, prev, cur)
            prev = cur
