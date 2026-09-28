#!/usr/bin/env python3
"""DEEPSIFT v1 research figures — drawn from frozen artifacts only (no recomputation).

    uv run python scripts/make_release_figures.py

Reads artifacts/phase3_final/<run>/results.json (final-test summary + four-period table, which already contains the
development / validation1 / validation2 values computed by the frozen runner) and apps/web/data/release.json (research
funnel verdicts + replay geometry, itself built from frozen artifacts). Writes docs/figures/fig{1..5}.{svg,png} and copies
the SVGs to apps/web/public/figures/.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "artifacts/phase3_final/20260926T174018-phase3-final-test-e4e2/results.json"
REL = ROOT / "apps/web/data/release.json"
OUT = ROOT / "docs" / "figures"
WEB = ROOT / "apps" / "web" / "public" / "figures"
# Okabe–Ito (colour-blind safe) + distinct markers; identity never by colour alone
METHODS = [("SEND_ALL", "SEND ALL", "#000000", "*"), ("EVERY_NTH_FRAME", "EVERY Nth", "#E69F00", "s"),
           ("UNIFORM_DISTANCE", "UNIFORM DISTANCE", "#56B4E9", "^"), ("METADATA_POSITION", "POSITION", "#0072B2", "o"),
           ("POSITION_PLUS_EMBEDDING_CHANGE", "POSITION + EMBEDDING", "#D55E00", "D")]
PERIODS = [("DEVELOPMENT 412–430", "Development\n412–430"), ("VALIDATION1 779–820", "Validation 1\n779–820"),
           ("VALIDATION2 1100–1129", "Validation 2\n1100–1129"), ("TEST 950–979", "Held-out test\n950–979")]
STYLE = {"font.size": 9, "font.family": "DejaVu Sans", "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
         "grid.alpha": 0.25, "figure.dpi": 150, "savefig.bbox": "tight", "legend.frameon": False, "svg.fonttype": "path"}
NOTE = "Retrospective replay of archived (downlinked) PDS observations · not onboard reconstruction"


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    WEB.mkdir(parents=True, exist_ok=True)
    for ext in ("svg", "png"):
        fig.savefig(OUT / f"{name}.{ext}")
    shutil.copy(OUT / f"{name}.svg", WEB / f"{name}.svg")
    plt.close(fig)


def main() -> int:
    plt.rcParams.update(STYLE)
    R = json.loads(FINAL.read_text())
    S = R["traverse"]["summary"]
    rel = json.loads(REL.read_text())

    # ---- Figure 1: bytes retained vs spatial coverage and vs largest distance to a kept frame (held-out test)
    fig, ax = plt.subplots(1, 2, figsize=(10.4, 3.8), gridspec_kw={"wspace": 0.38})
    for key, label, col, mk in METHODS:
        pts = [(1.0, S["1.0|SEND_ALL"])] if key == "SEND_ALL" else [(f, S[f"{f}|{key}"]) for f in (0.5, 0.25, 0.125)]
        xs = [p["bytes_fraction"] for _, p in pts]
        ax[0].plot(xs, [p["coverage_5m"] for _, p in pts], marker=mk, color=col, label=label, lw=1.2, ms=6)
        ax[1].plot(xs, [p["max_distance_to_kept_m_worst"] for _, p in pts], marker=mk, color=col, label=label, lw=1.2, ms=6)
    for a in ax:
        a.set_xlabel("Bytes retained (fraction of SEND ALL, full-quality traverse)")
        a.axvline(S["0.25|METADATA_POSITION"]["bytes_fraction"], color="#999999", lw=0.8, ls=":")
    ax[0].set_ylabel("5 m spatial coverage")
    ax[0].set_ylim(0.93, 1.005)
    ax[0].axhline(0.90, color="#999999", lw=0.8, ls="--")
    ax[1].set_ylabel("Largest distance to a kept frame\n(m, worst sequence)")
    ax[1].axhline(10, color="#999999", lw=0.8, ls="--")
    ax[1].text(0.52, 10.4, "pre-registered limit 10 m", fontsize=7, color="#555555")
    ax[0].legend(fontsize=7, loc="lower right")
    fig.suptitle("Figure 1 · Held-out test (Curiosity Navcam, sols 950–979): bytes vs spatial coverage — 12 traverses, 679 frames", fontsize=9.5, x=0.01, ha="left")
    fig.text(0.01, -0.03, NOTE + " · points at 1/8, 1/4, 1/2 retention; dotted line = POSITION at 1/4", fontsize=7, color="#555555")
    save(fig, "fig1_bytes_vs_coverage")

    # ---- Figure 2: four-period generalization of POSITION at 1/4
    four = R["four_period"]
    fig, ax = plt.subplots(1, 4, figsize=(12.0, 3.2))
    labels = ["Dev\n412–430", "Val 1\n779–820", "Val 2\n1100–1129", "Test\n950–979"]
    specs = [("bytes_fraction", "Bytes fraction (≤ 0.35)", 0.35, (0, 0.4)), ("coverage_5m", "5 m coverage (≥ 0.90)", 0.90, (0.8, 1.02)),
             ("max_distance_to_kept_m_worst", "Largest distance to kept, m (≤ 10)", 10, (0, 11)), ("stereo_broken", "Broken stereo pairs (= 0)", None, (0, 1))]
    for a, (m, title, lim, yl) in zip(ax, specs):
        vals = [four[k]["POSITION"][m] for k, _ in PERIODS]
        cols = ["#999999", "#999999", "#999999", "#0072B2"]
        a.bar(range(4), vals if m != "stereo_broken" else [0.02] * 4, color=cols, width=0.6)
        for i, v in enumerate(vals):
            a.text(i, (v if m != "stereo_broken" else 0.02) + (yl[1] - yl[0]) * 0.02, f"{v:.3f}" if isinstance(v, float) and m != "max_distance_to_kept_m_worst" else
                   (f"{v:.2f}" if isinstance(v, float) else str(v)), ha="center", fontsize=7.5)
        if lim is not None:
            a.axhline(lim, color="#555555", lw=0.8, ls="--")
        a.set_xticks(range(4), labels, fontsize=6.5)
        a.set_ylim(*yl)
        a.set_title(title, fontsize=8.5)
        if m == "stereo_broken":
            a.set_yticks([0, 1])
    fig.suptitle("Figure 2 · Scheduler V3 + POSITION at 1/4 retention across four non-pooled periods (dashed = pre-registered limit)",
                 fontsize=9.5, x=0.01, ha="left")
    fig.text(0.01, -0.06, NOTE + " · the limit is the final-test criterion; earlier periods recomputed by the frozen runner", fontsize=7, color="#555555")
    fig.tight_layout()
    save(fig, "fig2_four_period_generalization")

    # ---- Figure 3: embedding gain over POSITION, by period
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    for i, (k, lab) in enumerate(PERIODS):
        g = four[k]["embedding_gain"]
        lo, hi = g["visual_change_gain_95ci"]
        v = g["visual_change_gain"]
        ax.errorbar(i, v, yerr=[[v - lo], [hi - v]], fmt="o" if i < 3 else "D", color="#D55E00" if i == 0 else "#0072B2", capsize=4, ms=6)
        ax.text(i + 0.12, v, f"{v:+.3f}", va="center", fontsize=8)
    ax.axhline(0.020, color="#555555", ls="--", lw=0.8)
    ax.text(3.45, 0.021, "pre-registered\n'meaningful' = 0.020", fontsize=7, color="#555555", va="bottom", ha="right")
    ax.axhline(0, color="#000000", lw=0.6)
    ax.set_xticks(range(4), [lab for _, lab in PERIODS], fontsize=7.5)
    ax.set_xlim(-0.5, 3.6)
    ax.set_ylabel("Visual-change gain\n(POSITION+EMBEDDING − POSITION)")
    fig.suptitle("Figure 3 · The development embedding gain did not persist (1/4 retention, 95 % sequence-bootstrap CI)", fontsize=9.5, x=0.01, ha="left")
    fig.text(0.01, -0.05, "Visual-change coverage is a MobileNetV2 embedding proxy, not a scientific judgement", fontsize=7, color="#555555")
    save(fig, "fig3_embedding_gain_by_period")

    # ---- Figure 4: research funnel (verdicts, not a leaderboard)
    fun = rel["funnel"]
    fig, ax = plt.subplots(figsize=(10.5, 0.52 * len(fun) + 0.9))
    fig.subplots_adjust(left=0.01, right=0.99)
    ax.axis("off")
    colours = {"DROP": "#555555", "NO MEASURABLE ADDED VALUE": "#E69F00", "KEEP": "#0072B2"}
    for i, f in enumerate(fun):
        y = len(fun) - i
        ax.text(0.0, y, f["name"], fontsize=9, va="center", weight="bold")
        ax.text(0.40, y, f["verdict"], fontsize=8.5, va="center", color="white",
                bbox={"boxstyle": "round,pad=0.3", "fc": colours[f["verdict"]], "ec": "none"})
        ax.text(0.72, y, f["phase"], fontsize=7.5, va="center", color="#555555")
    ax.set_ylim(0.3, len(fun) + 0.7)
    ax.set_xlim(0, 1)
    fig.suptitle("Figure 4 · What survived the research funnel (evidence and sources in apps/web/data/release.json → funnel)", fontsize=9.5, x=0.01, ha="left")
    save(fig, "fig4_research_funnel")

    # ---- Figure 5: example final-test traverse (fixed rule: longest path; not claimed statistically representative)
    rep = next(s for s in rel["replay"]["sequences"] if s["sequence"] == rel["replay"]["representative"])
    kept = set(rep["kept_position"]["0.25"])
    pts = rep["points"]
    fig, ax = plt.subplots(figsize=(7.2, 5.4))
    xs, ys = [p["x"] for p in pts], [p["y"] for p in pts]
    ax.plot(xs, ys, color="#bbbbbb", lw=1, zorder=1)
    for j in kept:
        ax.add_patch(Circle((xs[j], ys[j]), 5.0, fc="#0072B2", alpha=0.08, ec="#0072B2", lw=0.5, zorder=0))
    for j, p in enumerate(pts):
        if j not in kept:
            nk = min(kept, key=lambda k: (xs[k] - p["x"]) ** 2 + (ys[k] - p["y"]) ** 2)
            ax.plot([p["x"], xs[nk]], [p["y"], ys[nk]], color="#E69F00", lw=0.6, zorder=2)
    ax.scatter([xs[j] for j in range(len(pts)) if j not in kept], [ys[j] for j in range(len(pts)) if j not in kept], s=14, marker="o",
               facecolor="white", edgecolor="#555555", label=f"archived frame, thumbnail only ({len(pts) - len(kept)})", zorder=3)
    ax.scatter([xs[j] for j in kept], [ys[j] for j in kept], s=40, marker="s", color="#0072B2", label=f"kept by POSITION at full quality ({len(kept)})", zorder=4)
    m = rep["metrics"]["0.25"]
    ax.set_aspect("equal")
    ax.set_xlabel("x relative to first frame (m, PLACES landing frame)")
    ax.set_ylabel("y relative to first frame (m)")
    ax.legend(fontsize=7.5, loc="best")
    fig.suptitle(f"Figure 5 · Held-out traverse {rep['sequence']} ({rep['frames']} frames, {rep['length_m']:.0f} m): shaded = 5 m radius, orange = distance to nearest kept frame",
                 fontsize=9, x=0.01, ha="left")
    fig.text(0.01, 0.0, f"This traverse at 1/4: 5 m coverage {m['position_coverage']:.3f} · largest distance to kept {m['max_distance_to_kept_m']:.2f} m · "
             f"bytes {m['bytes'] / m['bytes_send_all']:.3f} of SEND ALL · broken stereo {m['stereo_broken']} · rule: longest-path traverse", fontsize=7, color="#555555")
    save(fig, "fig5_example_traverse")
    print("figures →", OUT.relative_to(ROOT), "and", WEB.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
