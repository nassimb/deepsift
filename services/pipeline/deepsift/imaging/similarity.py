"""M7 — near-duplicate grouping (strategy input) and metadata SCENE clusters (evaluation reference).

Declared a priori:
  PHASH near-duplicate link: same sol AND Hamming(pHash) ≤ PHASH_MAX_BITS (10 of 64). Groups = connected components.
  SEQUENCE grouping (metadata baseline): same sol AND same sequence id.
  SCENE cluster (evaluation only, pixel-free, so pixel-based strategies are not graded on their own clusters):
      same rover stop (site, drive, pose) AND pointing within SCENE_MAX_DEG (15°) in azimuth and elevation.
"""

from __future__ import annotations

from collections import defaultdict

from deepsift.imaging.features import hamming

PHASH_MAX_BITS = 10
SCENE_MAX_DEG = 15.0


class _UF:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, i: int) -> int:
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, a: int, b: int) -> None:
        self.p[self.find(a)] = self.find(b)


def _components(n: int, pairs) -> list[int]:
    uf = _UF(n)
    for a, b in pairs:
        uf.union(a, b)
    roots = {}
    return [roots.setdefault(uf.find(i), len(roots)) for i in range(n)]


def phash_groups(acqs: list[dict], hashes: list[int]) -> list[int]:
    by_sol = defaultdict(list)
    for i, a in enumerate(acqs):
        by_sol[a["sol"]].append(i)
    pairs = [(i, j) for idx in by_sol.values() for k, i in enumerate(idx) for j in idx[k + 1:] if hamming(hashes[i], hashes[j]) <= PHASH_MAX_BITS]
    return _components(len(acqs), pairs)


def sequence_groups(acqs: list[dict]) -> list[int]:
    keys = {}
    return [keys.setdefault((a["sol"], a["sequence_id"]), len(keys)) for a in acqs]


def _angdiff(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def scene_clusters(acqs: list[dict]) -> list[int]:
    by_stop = defaultdict(list)
    for i, a in enumerate(acqs):
        by_stop[(a["site"], a["drive"], a["pose"])].append(i)
    pairs = []
    for idx in by_stop.values():
        for k, i in enumerate(idx):
            for j in idx[k + 1:]:
                ai, aj = acqs[i], acqs[j]
                if None in (ai["azimuth_deg"], aj["azimuth_deg"], ai["elevation_deg"], aj["elevation_deg"]):
                    continue
                if _angdiff(ai["azimuth_deg"], aj["azimuth_deg"]) <= SCENE_MAX_DEG and abs(ai["elevation_deg"] - aj["elevation_deg"]) <= SCENE_MAX_DEG:
                    pairs.append((i, j))
    return _components(len(acqs), pairs)


def group_stats(groups: list[int], full_bytes: list[float | None]) -> dict:
    members = defaultdict(list)
    for i, g in enumerate(groups):
        members[g].append(i)
    sizes = sorted((len(v) for v in members.values()), reverse=True)
    multi = [v for v in members.values() if len(v) > 1]
    # redundant = full-product bytes of every member except the single largest-byte member of its group
    red = 0.0
    for v in multi:
        b = sorted((full_bytes[i] or 0.0 for i in v), reverse=True)
        red += sum(b[1:])
    return {"acquisitions": len(groups), "groups": len(members), "groups_with_duplicates": len(multi),
            "acquisitions_in_duplicate_groups": sum(len(v) for v in multi), "mean_group_size": len(groups) / max(1, len(members)),
            "largest_group": sizes[0] if sizes else 0, "estimated_redundant_downlink_bytes": red,
            "total_full_downlink_bytes": float(sum(b or 0.0 for b in full_bytes))}
