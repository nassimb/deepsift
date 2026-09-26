"""Phase 3 DEFAULT pipeline after validation (Phase 3.4 simplification).

PRIMARY PATH (kept on validation evidence, Phase 3.3):
    Scheduler V3 (SCHEDULER_V3_STEREO_SAFE, image_benchmark.allocate_progressive over cost_table_v3)
    rover-position sampling (traverse METADATA_POSITION)
    MobileNetV2 embedding-change signal (traverse EMBEDDING_CHANGE; global EMBEDDING-NOVELTY order)
    POSITION + EMBEDDING_CHANGE (traverse)
  with comparison baselines FIFO, RANDOM, SIZE_AWARE, EVERY_NTH_FRAME, UNIFORM_DISTANCE.

EXPERIMENTAL / DIAGNOSTIC ONLY (code kept for reproducibility; never used to prioritize, demote or discard):
    pHash representative selection      — constrained false merge 0.15–0.19 on validation, ≤ 1.03× compression
    QUALITY_V2                          — validation FPR 10.6 % vs development 3.6 %; may only raise QUALITY_SUSPECT
    telemetry ranking                   — dropped in Phase 3.2; telemetry is descriptive metadata
    Jev ranking / Jev pairwise          — auxiliary diagnostic, never ranking or ground truth
"""

from __future__ import annotations

from deepsift.evaluation import image_benchmark as ib
from deepsift.evaluation import traverse

PRIMARY_SCHEDULER = ib.SCHEDULER_V3_STEREO_SAFE
PRIMARY_TRAVERSE_METHODS = ["METADATA_POSITION", "EMBEDDING_CHANGE", "POSITION_PLUS_EMBEDDING_CHANGE"]
BASELINE_TRAVERSE_METHODS = ["EVERY_NTH_FRAME", "UNIFORM_DISTANCE"]
PRIMARY_GLOBAL_ORDERS = ["FIFO", "RANDOM", "SIZE_AWARE", "EMBEDDING_CHANGE"]
DIAGNOSTIC_ONLY = {
    "PHASH_REPRESENTATIVES": "diagnostic similarity / local duplicate hints / research comparison only",
    "QUALITY_V2": "diagnostic only: may flag QUALITY_SUSPECT, may not lower or remove an observation",
    "TELEMETRY_PRIORITY": "descriptive metadata only",
    "JEV": "auxiliary diagnostic only",
}
QUALITY_SUSPECT, QUALITY_NOT_FLAGGED = "QUALITY_SUSPECT", "QUALITY_NOT_FLAGGED"


def primary_orders(obs: list[dict], seed: int = 0) -> dict[str, list[int]]:
    """Global downlink orders of the primary path. Built from capture time, full-product size and embedding novelty
    only — pHash groups, quality state, telemetry and Jev never enter."""
    o = ib.strategy_orders(obs, seed)
    return {"FIFO": o["FIFO"], "RANDOM": o["RANDOM"], "SIZE_AWARE": o["SIZE-AWARE"], "EMBEDDING_CHANGE": o["EMBEDDING-NOVELTY"]}


def allocate_primary(cost_table_v3: list[dict], order: list[int], budget: float) -> list[str]:
    return ib.allocate_progressive(cost_table_v3, order, budget)


def select_traverse(method: str, xy, emb, frac: float) -> list[int]:
    if method not in PRIMARY_TRAVERSE_METHODS + BASELINE_TRAVERSE_METHODS:
        raise ValueError(f"{method} is not part of the Phase 3 primary path")
    return traverse.select(method, xy, emb, frac)


def quality_flag(classification: tuple[str, list[str]]) -> dict:
    """Map a QUALITY_V2 classification to a DIAGNOSTIC flag. The flag is attached to the observation for humans;
    no primary-path function reads it."""
    state, reasons = classification
    return {"flag": QUALITY_NOT_FLAGGED if state == "CLEAN" else QUALITY_SUSPECT, "reasons": list(reasons),
            "role": "DIAGNOSTIC ONLY — does not affect downlink ranking"}
