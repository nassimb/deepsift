#!/usr/bin/env python3
"""Public-claims checklist: every public-facing number, its displayed form and its exact frozen source.

    uv run python scripts/check_public_claims.py            # verify every claim against the frozen artifacts (exit 1 on mismatch)
    uv run python scripts/check_public_claims.py --write    # also regenerate docs/public-claims-checklist.md

The displayed strings below are the ones used in the README, paper, one-pager, posts, video and web app. Each is recomputed
from its source file and JSON path; a mismatch means the public text is wrong, not the artifact.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINAL = "artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json"
DS = "artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/dataset_report.json"
CFG = "config/phase3_final_test_config.json"
VAL1 = "artifacts/phase3_3/20260926T142033-phase3.3-val-2a31/results.json"
P32 = "artifacts/phase3_2/20260925T135920-phase3.2-dev-corrective-ceb8/results.json"
HOME = "apps/web/data/home-summary.json"
REL = "apps/web/data/release.json"
FP = "four_period"

pct1 = lambda v: f"{v * 100:.1f}%"  # noqa: E731
pct0 = lambda v: f"{v * 100:.0f}%"  # noqa: E731
m2 = lambda v: f"{v:.2f} m"  # noqa: E731
f3 = lambda v: f"{v:.3f}"  # noqa: E731
sg3 = lambda v: f"{v:+.3f}"  # noqa: E731
i0 = lambda v: f"{v:,}"  # noqa: E731

# (claim, displayed value, source file, json path, formatter)
CLAIMS = [
    ("Final test: full-quality traverse bytes at 1/4 retention", "26.1%", FINAL, "primary.metrics.bytes_fraction", pct1),
    ("Final test: 5 m spatial coverage", "100%", FINAL, "primary.metrics.coverage_5m", pct0),
    ("Final test: 5 m spatial coverage (exact)", "1.000", FINAL, "primary.metrics.coverage_5m", f3),
    ("Final test: max distance from any archived frame to a retained frame", "2.05 m", FINAL, "primary.metrics.max_distance_to_kept_m_worst", m2),
    ("Final test: broken stereo pairs", "0", FINAL, "primary.metrics.stereo_broken", str),
    ("Final test: stereo pairs kept whole at full quality", "174", FINAL, "primary.metrics.stereo_kept_full", str),
    ("Final test: primary criterion result", "PASS", FINAL, "primary.RESULT", str),
    ("Final test: Scheduler V3 monotonicity violations", "0", FINAL, "scheduler_v3.total_violations", str),
    ("Final test: single-eye usable stereo pairs", "0", FINAL, "scheduler_v3.single_eye_usable_violations", str),
    ("Final test: retention fraction (1/4)", "0.25", CFG, "evaluation.primary_fraction", str),
    ("Final test: bytes criterion", "0.35", CFG, "primary.PASS_iff_all.P1", lambda v: "0.35" if "0.35" in v else v),
    ("Final test: distance criterion", "10 m", CFG, "primary.PASS_iff_all.P3", lambda v: "10 m" if "10 m" in v else v),
    ("Final test: config hash", "6f35d7fc", CFG, "config_hash", lambda v: v[:8]),
    ("Final test: traverse sequences", "12", DS, "traverse_sequences_ge_10_frames", str),
    ("Final test: archived traverse frames", "679", DS, "traverse_frames", str),
    ("Final test: active sols", "25", DS, "n_active_sols", str),
    ("Final test: Navcam acquisitions", "1,194", DS, "acquisitions", i0),
    ("Final test: PDS products", "4,342", DS, "products", i0),
    ("Final test: POSITION visual-change coverage (descriptive)", "0.950", FINAL, "secondary_embedding.position_visual_1_4", f3),
    ("Final test: POSITION+EMBEDDING visual-change coverage", "0.956", FINAL, "secondary_embedding.position_plus_embedding_visual_1_4", f3),
    ("Final test: embedding visual-change gain", "+0.005", FINAL, "secondary_embedding.by_fraction.0.25.visual_change_gain", sg3),
    ("Final test: embedding secondary conclusion", "NO MEASURABLE ADDED VALUE", FINAL, "secondary_embedding.CONCLUSION", str),
    ("Final test: POSITION+EMBEDDING max distance to kept", "4.89 m", FINAL, "traverse.summary.0.25|POSITION_PLUS_EMBEDDING_CHANGE.max_distance_to_kept_m_worst", m2),
    ("Final test: EVERY_NTH max distance to kept", "20.04 m", FINAL, "traverse.summary.0.25|EVERY_NTH_FRAME.max_distance_to_kept_m_worst", m2),
    ("Embedding gain, development", "+0.044", FINAL, f"{FP}.DEVELOPMENT 412–430.embedding_gain.visual_change_gain", sg3),
    ("Embedding gain, validation 1", "+0.004", FINAL, f"{FP}.VALIDATION1 779–820.embedding_gain.visual_change_gain", sg3),
    ("Embedding gain, validation 2", "+0.001", FINAL, f"{FP}.VALIDATION2 1100–1129.embedding_gain.visual_change_gain", sg3),
    ("Embedding gain, held-out test", "+0.005", FINAL, f"{FP}.TEST 950–979.embedding_gain.visual_change_gain", sg3),
    ("POSITION 5 m coverage, development", "1.000", FINAL, f"{FP}.DEVELOPMENT 412–430.POSITION.coverage_5m", f3),
    ("POSITION 5 m coverage, validation 1", "1.000", FINAL, f"{FP}.VALIDATION1 779–820.POSITION.coverage_5m", f3),
    ("POSITION 5 m coverage, validation 2", "1.000", FINAL, f"{FP}.VALIDATION2 1100–1129.POSITION.coverage_5m", f3),
    ("POSITION max distance to kept, development", "2.64 m", FINAL, f"{FP}.DEVELOPMENT 412–430.POSITION.max_distance_to_kept_m_worst", m2),
    ("POSITION max distance to kept, validation 1", "2.78 m", FINAL, f"{FP}.VALIDATION1 779–820.POSITION.max_distance_to_kept_m_worst", m2),
    ("POSITION max distance to kept, validation 2", "1.94 m", FINAL, f"{FP}.VALIDATION2 1100–1129.POSITION.max_distance_to_kept_m_worst", m2),
    ("POSITION bytes, development", "0.266", FINAL, f"{FP}.DEVELOPMENT 412–430.POSITION.bytes_fraction", f3),
    ("POSITION bytes, validation 1", "0.265", FINAL, f"{FP}.VALIDATION1 779–820.POSITION.bytes_fraction", f3),
    ("POSITION bytes, validation 2", "0.270", FINAL, f"{FP}.VALIDATION2 1100–1129.POSITION.bytes_fraction", f3),
    ("Jev: AUROC difference vs deterministic rules", "+0.006", HOME, "jev.auroc_diff_vs_rules.with_objective.diff", sg3),
    ("Jev: AUROC difference 95 % CI lower", "-0.020", HOME, "jev.auroc_diff_vs_rules.with_objective.ci95.0", lambda v: f"{v:.3f}"),
    ("Jev: AUROC difference 95 % CI upper", "+0.037", HOME, "jev.auroc_diff_vs_rules.with_objective.ci95.1", sg3),
    ("Jev: live calls in the final design pilot", "1,500", HOME, "jev.live_calls", i0),
    ("Telemetry ranking: usable acquisitions at 1 % (Scheduler V3)", "7", P32, "schedulers.comparison.V3|TELEMETRY-PRIORITY|0.01.acquisitions_usable", str),
    ("Telemetry ranking: rover positions at 1 %", "1", P32, "schedulers.comparison.V3|TELEMETRY-PRIORITY|0.01.rover_positions_usable", str),
    ("QUALITY_V2 false-positive rate, development", "3.6%", VAL1, "quality_v2_real.development_fpr", pct1),
    ("QUALITY_V2 false-positive rate, validation 1", "10.6%", VAL1, "quality_v2_real.overall", pct1),
    ("Constrained pHash false merge, validation 1 (+120 s)", "0.15", VAL1, "phash.PHASH_PLUS_TIME_120S.false_merge_rate_different_scene", lambda v: f"{v:.2f}"),
    ("Constrained pHash false merge, validation 1 (+same stop)", "0.19", VAL1, "phash.PHASH_PLUS_SAME_ROVER_STOP.false_merge_rate_different_scene", lambda v: f"{v:.2f}"),
    ("Constrained pHash traverse compression (max)", "1.03×", VAL1, "phash.PHASH_PLUS_TIME_120S.traverse_compression", lambda v: f"{v:.2f}×"),
    ("Test config committed before first test image", "True", REL, "reproducibility.frozen_before_download.config_before_download", str),
    ("Test config commit time", "2026-09-26T13:03:26-04:00", REL, "reproducibility.frozen_before_download.config_commit_time", str),
    ("First test image written (UTC)", "2026-09-26T17:03:50", REL, "reproducibility.frozen_before_download.first_test_image_written", lambda v: v[:19]),
    ("Scientific artifacts under integrity manifest", "70", "docs/release/science-artifacts.json", "files", str),
]

MANUAL = [
    "Replace every {{DEMO_URL}} placeholder with the deployed site URL (the GitHub URL is already filled in: https://github.com/nassimb/deepsift).",
    "No text says or implies NASA/JPL endorsement, use, review or validation; no NASA logo or insignia in any media.",
    "No 'flight-ready', 'production-ready', 'NASA-grade', 'breakthrough', 'revolutionary'.",
    "No claim of scientific-value preservation or onboard-stream reconstruction; the PDS survivorship-bias caveat accompanies the headline result.",
    "The compressed stereo tier is called a SIMULATED product tier wherever it is mentioned.",
    "Visual-change coverage is described as an embedding proxy, never as scientific value.",
    "Jev results are described as specific to the tested role (ranking already-detected REMS/RAD candidates), not a general claim about the model.",
    "uv run python scripts/release_integrity.py --verify prints INTACT.",
    "uv run python scripts/check_public_claims.py exits 0.",
]


def get(obj, path: str):
    """Walk a dotted path; keys may themselves contain dots or pipes, so greedily match the longest existing key."""
    parts = path.split(".")
    cur, i = obj, 0
    while i < len(parts):
        for j in range(len(parts), i, -1):
            key = ".".join(parts[i:j])
            if isinstance(cur, dict) and key in cur:
                cur, i = cur[key], j
                break
            if isinstance(cur, list) and key.isdigit() and int(key) < len(cur):
                cur, i = cur[int(key)], j
                break
        else:
            raise KeyError(path)
    return cur


def main() -> int:
    cache: dict[str, dict] = {}
    rows, bad = [], 0
    for claim, shown, src, path, fmt in CLAIMS:
        data = cache.setdefault(src, json.loads((ROOT / src).read_text()))
        v = get(data, path)
        got = fmt(v)
        ok = got == shown
        bad += not ok
        rows.append((claim, shown, got, ok, src, path))
        if not ok:
            print(f"MISMATCH: {claim}: public '{shown}' vs artifact '{got}' ({src} → {path})")
    print(f"{len(rows) - bad}/{len(rows)} public claims match their frozen sources")
    if "--write" in sys.argv:
        md = ["# DEEPSIFT — public claims checklist", "",
              "Run before publishing anything: `uv run python scripts/check_public_claims.py` (regenerate this file with `--write`).",
              "Every number below is recomputed from its frozen source; ✅ means the public wording matches the artifact exactly.", "",
              "## Numerical claims", "", "| # | claim | public value | check | source | JSON path |", "|---|---|---|---|---|---|"]
        for k, (claim, shown, got, ok, src, path) in enumerate(rows, 1):
            md.append(f"| {k} | {claim} | **{shown}** | {'✅' if ok else '❌ ' + got} | `{src}` | `{path}` |")
        md += ["", "## Manual checks before publishing", ""] + [f"- [ ] {m}" for m in MANUAL] + [""]
        (ROOT / "docs" / "public-claims-checklist.md").write_text("\n".join(md))
        print("→ docs/public-claims-checklist.md")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
