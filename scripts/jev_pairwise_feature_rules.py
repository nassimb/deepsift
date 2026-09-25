#!/usr/bin/env python3
"""Post-hoc diagnostic (Phase 3.2): how well do single-feature rules over the EXACT text state Jev received reproduce its
JEV PAIRWISE PREFERENCE? Uses stored states + calls only (no network). Explains Jev; does not validate it.

    uv run python scripts/jev_pairwise_feature_rules.py [artifacts/phase3_2/<jev run dir>]
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _v(x):
    return x if isinstance(x, (int, float)) else None


def prev_change(a, b):
    f = lambda s: _v(s["visual_difference_from_previous_frame_in_same_sequence"])  # noqa: E731
    return (f(a) if f(a) is not None else 9) - (f(b) if f(b) is not None else 9)   # first frame of a sequence = maximal change


RULES = {
    "larger_previous_frame_visual_difference": prev_change,
    "higher_entropy": lambda a, b: a["image_quality"]["entropy_bits"] - b["image_quality"]["entropy_bits"],
    "stereo_over_single_eye": lambda a, b: a["stereo"].startswith("left") - b["stereo"].startswith("left"),
    "full_frame_over_downsampled": lambda a, b: ("1024" in a["product_resolution"]) - ("1024" in b["product_resolution"]),
    "larger_downlink_bytes": lambda a, b: a["full_quality_downlink_kilobytes"] - b["full_quality_downlink_kilobytes"],
    "fewer_acquisitions_at_same_position": lambda a, b: (b["acquisitions_in_this_development_set_at_the_same_rover_position"]
                                                         - a["acquisitions_in_this_development_set_at_the_same_rover_position"]),
    "telemetry_event_nearby": lambda a, b: ((a["environmental_telemetry_event_within_30_min"] == "yes")
                                            - (b["environmental_telemetry_event_within_30_min"] == "yes")),
}


def main() -> int:
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted((ROOT / "artifacts" / "phase3_2").glob("*-jev-pairwise-*"))[-1]
    st = {(x["pair_id"], x["order"]): x["state"] for x in map(json.loads, (d / "states.jsonl").open())}
    calls = [x for x in map(json.loads, (d / "calls.jsonl").open())
             if x.get("repeat") == 0 and "phase" not in x and x["choice"] in ("A", "B")]
    out = {}
    for name, f in RULES.items():
        k = n = 0
        for c in calls:
            s = st[(c["pair_id"], c["order"])]
            v = f(s["observation_A"], s["observation_B"])
            if v == 0:
                continue
            n += 1
            k += (c["choice"] == "A") == (v > 0)
        out[name] = {"n_decisive_calls": n, "agreement": round(k / n, 3) if n else None}
    res = {"label": "JEV PAIRWISE PREFERENCE — post-hoc feature-rule alignment (AB and BA main calls)", "rules": out}
    (d / "feature_rule_alignment.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
