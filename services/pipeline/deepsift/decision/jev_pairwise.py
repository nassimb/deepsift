"""JEV PAIRWISE REVIEWER (Phase 3.2, experimental, TEXT-ONLY).

Jev receives a structured TEXT summary of two archived Navcam acquisitions built from metadata and features that DEEPSIFT
already computed. It never receives images, image URLs, captions, scene descriptions or any vision-language output, and
must never be described as seeing images. It never receives strategy names, strategy ranks, strategy scores (embedding
novelty, telemetry score), winner labels, an aggregate "science value", algorithm preferences, ground truth or human
preferences. Its answers are recorded as JEV PAIRWISE PREFERENCE — not human review, not expert review, not scientific
ground truth, not NASA-like review — and are never used to tune anything.

Cache key (sha256 of canonical JSON) = { schema_version, order ("AB"/"BA"), state (both sides, in presented order),
questions, model_requested, expected_snapshot, sdk_version, transport }. A cached entry is used only if its recorded
returned snapshot equals the expected snapshot, so the served snapshot is part of the cache identity.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from deepsift.core.config import DATA_DIR
from deepsift.decision.questions import QuestionSpec

SCHEMA_VERSION = "JEV_PAIRWISE_V1"
LABEL = "JEV PAIRWISE PREFERENCE"
EXPECTED_SNAPSHOT = "typesafe/jev-1.13-20260917"
FORBIDDEN_LABELS = ("HUMAN REVIEW", "SCIENTIFIC GROUND TRUTH", "EXPERT REVIEW", "NASA-LIKE REVIEW")

PRIORITY_QUESTION = ("If only one of these two observations could be downlinked at useful image quality, which should be "
                     "prioritized to preserve useful mission coverage under bandwidth constraints?")
QUESTIONS: dict[str, QuestionSpec] = {
    "priority": QuestionSpec("choice", PRIORITY_QUESTION, {
        "A": "Observation A should be prioritized",
        "B": "Observation B should be prioritized",
        "EQUAL": "Both are equally worth prioritizing",
        "UNSURE": "The summary does not give enough information to decide",
    }),
    "reason": QuestionSpec("choice", "What is the main reason for that choice?", {
        "SPATIAL_COVERAGE": "It covers a rover position or area the other does not",
        "VISUAL_CHANGE": "It records more change relative to nearby earlier frames",
        "IMAGE_QUALITY": "Its image quality indicators are better",
        "BANDWIDTH_EFFICIENCY": "It costs fewer bytes for similar coverage",
        "STEREO_VALUE": "It preserves a stereo pair (both eyes)",
        "NO_CLEAR_ADVANTAGE": "Neither observation has a clear advantage",
    }),
}

# Keys and substrings that must never appear in a state sent to Jev (checked by `assert_clean`).
FORBIDDEN_STATE_TOKENS = ("rank", "novelty", "telemetry_score", "score", "strategy", "fifo", "size-aware", "size_aware",
                          "phash_rep", "winner", "science_value", "ground_truth", "human", "category", "url", "http",
                          ".img", "image_url", "caption", "description", "acq_id", "MSL-NAV")

_SEQ = {"trav": "TRAV", "ncam": "NCAM", "sapp": "SAPP"}


def _r(x, nd=3):
    return None if x is None else float(f"{x:.{nd}g}")


def side_summary(o: dict, full_kb_pair: float, prev_change: float | None, quality_v2: str, pose_count: int) -> dict:
    f = o["image_features"]
    tel = o["telemetry_context"]
    return {
        "camera": "Navcam (engineering camera, grayscale)",
        "stereo": "left+right pair" if o["stereo"] else "single eye",
        "product_resolution": {"F": "1024x1024 full frame", "D": "256x256 downsampled", "S": "subframe", "M": "511x511"}.get(o["primary_tier"], o["primary_tier"]),
        "sequence_type_code": _SEQ.get(o["sequence_id"][:4].lower(), "OTHER"),
        "sol": o["sol"],
        "rover_position_site_drive_pose": list(o["source_metadata"]["pose"]),
        "acquisitions_in_this_development_set_at_the_same_rover_position": pose_count,
        "full_quality_downlink_kilobytes": _r(full_kb_pair),
        "image_quality": {
            "automatic_quality_check": quality_v2,
            "mean_brightness_0_to_1": _r(f["brightness"]), "contrast": _r(f["contrast"]), "entropy_bits": _r(f["entropy_bits"]),
            "sharpness": _r(f["sharpness"]), "saturated_fraction": _r(f["saturated_fraction"]), "missing_fraction": _r(f["missing_fraction"]),
        },
        "visual_difference_from_previous_frame_in_same_sequence": "first frame of its sequence" if prev_change is None else _r(prev_change),
        "environmental_telemetry_event_within_30_min": "yes" if tel.get("context_events") else "no",
    }


def pair_state(a: dict, b: dict, relation: dict) -> dict:
    return {
        "task": "Compare two archived Mars rover Navcam observations using the structured metadata and features below. "
                "No image is provided; only these numbers and categories.",
        "mission": "MSL / Curiosity, Gale Crater, Mars",
        "setting": "Retrospective bandwidth-constrained prioritization of archived rover observations",
        "feature_notes": {
            "visual_difference_from_previous_frame_in_same_sequence": "cosine distance between image embeddings, 0 = identical, larger = more change",
            "visual_difference_between_A_and_B": "same scale",
            "pixel_hash_difference_bits_between_A_and_B": "0-64, small = pixel-similar",
            "full_quality_downlink_kilobytes": "estimated bytes for all eyes at full quality",
        },
        "observation_A": a,
        "observation_B": b,
        "relation_between_A_and_B": relation,
    }


def relation(oa: dict, ob: dict, dist_m: float | None, cos_ab: float, ham_ab: int) -> dict:
    ta = datetime.fromisoformat(oa["utc"]).replace(tzinfo=timezone.utc)
    tb = datetime.fromisoformat(ob["utc"]).replace(tzinfo=timezone.utc)
    return {"same_sol": oa["sol"] == ob["sol"], "time_between_minutes": _r(abs((tb - ta).total_seconds()) / 60.0),
            "same_rover_position": oa["source_metadata"]["pose"] == ob["source_metadata"]["pose"],
            "distance_between_rover_positions_m": _r(dist_m) if dist_m is not None else "unknown",
            "same_scene_cluster_from_metadata": oa["scene_cluster"] == ob["scene_cluster"],
            "same_sequence": oa["sequence_id"] == ob["sequence_id"] and oa["sol"] == ob["sol"],
            "visual_difference_between_A_and_B": _r(cos_ab), "pixel_hash_difference_bits_between_A_and_B": int(ham_ab)}


def assert_clean(state: dict) -> None:
    """Raise if any forbidden token (strategy / score / image / identity leakage) appears in keys or string values."""
    def walk(x, path=""):
        if isinstance(x, dict):
            for k, v in x.items():
                for t in FORBIDDEN_STATE_TOKENS:
                    if t.lower() in k.lower():
                        raise ValueError(f"forbidden key token {t!r} in {path}/{k}")
                walk(v, f"{path}/{k}")
        elif isinstance(x, list):
            for v in x:
                walk(v, path)
        elif isinstance(x, str):
            for t in ("rank", "score", "strategy", "http", "MSL-NAV", ".IMG", "winner", "ground truth", "human"):
                if t.lower() in x.lower():
                    raise ValueError(f"forbidden value token {t!r} at {path}")
    walk(state)


def questions_payload() -> dict:
    return {n: {"type": q.kind, "instructions": q.instructions, "criteria": q.criteria} for n, q in QUESTIONS.items()}


def request_key(state: dict, order: str, model: str, snapshot: str, sdk_version: str, transport: str) -> str:
    blob = json.dumps({"schema_version": SCHEMA_VERSION, "order": order, "state": state, "questions": questions_payload(),
                       "model_requested": model, "expected_snapshot": snapshot, "sdk": sdk_version, "transport": transport},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


CACHE_PATH = DATA_DIR / "processed" / "jev_pairwise_cache.sqlite"
_lock = threading.Lock()


class PairwiseCache:
    """Versioned cache for pairwise answers (separate file from the Phase 2 event cache)."""

    def __init__(self, path: Path | None = None):
        self.path = path or CACHE_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as c:
            c.execute("CREATE TABLE IF NOT EXISTS pairwise (input_hash TEXT PRIMARY KEY, schema_version TEXT, pair_id TEXT, "
                      "ord TEXT, model_requested TEXT, model_returned TEXT, transport TEXT, provider TEXT, answers_json TEXT, "
                      "latency_ms REAL, input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL, created_at TEXT, run_id TEXT)")

    def get(self, key: str, expected_snapshot: str) -> dict | None:
        with sqlite3.connect(self.path) as c:
            row = c.execute("SELECT model_returned, provider, answers_json, latency_ms, input_tokens, output_tokens, cost_usd, run_id "
                            "FROM pairwise WHERE input_hash=?", [key]).fetchone()
        if not row or row[0] != expected_snapshot:
            return None
        return {"model_returned": row[0], "provider": row[1], "answers": json.loads(row[2]), "latency_ms": row[3],
                "input_tokens": row[4], "output_tokens": row[5], "cost_usd": row[6], "run_id": row[7]}

    def put(self, key: str, **r) -> None:
        with _lock, sqlite3.connect(self.path) as c:
            c.execute("INSERT OR IGNORE INTO pairwise VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
                key, SCHEMA_VERSION, r["pair_id"], r["order"], r["model_requested"], r["model_returned"], r["transport"],
                r["provider"], json.dumps(r["answers"]), r["latency_ms"], r["input_tokens"], r["output_tokens"], r["cost_usd"],
                datetime.now(timezone.utc).isoformat(), r["run_id"]])
