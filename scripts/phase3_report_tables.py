#!/usr/bin/env python3
"""Render Phase 3 baseline tables + figures from a stored run (no hand-typed numbers).

    uv run python scripts/phase3_report_tables.py <run_id>
Writes artifacts/phase3/<run_id>/tables.md and figures/*.png.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
STRATS = ["FIFO", "RANDOM", "SIZE-AWARE", "THUMBNAIL-EVERYTHING", "PHASH-REPRESENTATIVES", "EMBEDDING-NOVELTY", "TELEMETRY-PRIORITY"]


def key(s: str, mode: str) -> str:
    return s if s in ("THUMBNAIL-EVERYTHING", "PHASH-REPRESENTATIVES") else f"{s}|{mode}"


def main() -> int:
    run = ROOT / "artifacts" / "phase3" / sys.argv[1]
    b = json.loads((run / "benchmark.json").read_text())
    budgets = sorted({float(k.split("@")[1]) for k in b["results"]})
    R = b["results"]
    lines = [f"# Phase 3 baseline tables — {sys.argv[1]}", "", f"Budget base: {b['total_full_bytes'] / 1e6:.2f} MB (Σ FULL onboard-compressed bytes); "
             f"acquisitions with UNKNOWN full cost: {b['unknown_full_cost']}.", ""]
    metrics = [("scene_clusters_usable", "UNIQUE SCENE CLUSTERS retained at ≥ COMPRESSED (of {tot})", "scene_clusters_total"),
               ("scene_clusters_with_image", "SCENE CLUSTERS with any image (≥ THUMBNAIL)", None),
               ("unique_acquisitions_usable", "UNIQUE ACQUISITIONS retained at ≥ COMPRESSED", None),
               ("unique_acquisitions_with_image", "UNIQUE ACQUISITIONS with any image (≥ THUMBNAIL)", None),
               ("phash_groups_usable", "pHash GROUPS retained at ≥ COMPRESSED (secondary; circular for pHash strategy)", None),
               ("redundant_share_of_full_bytes", "NEAR-DUPLICATE SHARE of FULL bytes (same scene cluster; lower = less redundancy)", None),
               ("diversity_proxy_embedding_coverage", "OBSERVATION DIVERSITY PROXY — embedding coverage (circular for novelty strategy)", None),
               ("bytes_transmitted", "BYTES TRANSMITTED (kB)", None)]
    for mode in ("policy", "ordering"):
        lines += [f"## Mode: {mode}", "",
                  "*policy* = each strategy's own action policy; *ordering* = common thumbnails-for-all first pass, then FULL upgrades in "
                  "strategy order (THUMBNAIL-EVERYTHING and PHASH-REPRESENTATIVES are identical in both modes).", ""]
        for m, title, tot in metrics:
            total = R[f"{key('FIFO', mode)}@{budgets[0]}"].get(tot) if tot else None
            lines += [f"### {title.format(tot=total)}", "", "| strategy | " + " | ".join(f"{x * 100:g}%" for x in budgets) + " |",
                      "|---|" + "---|" * len(budgets)]
            for s in STRATS:
                cells = []
                for f in budgets:
                    v = R.get(f"{key(s, mode)}@{f}", {}).get(m)
                    if v is None:
                        cells.append("—")
                    elif m == "bytes_transmitted":
                        cells.append(f"{v / 1e3:.0f}")
                    elif isinstance(v, float) and v <= 1.0 and m in ("redundant_share_of_full_bytes", "diversity_proxy_embedding_coverage"):
                        cells.append(f"{v:.3f}")
                    else:
                        cells.append(f"{v:.1f}" if isinstance(v, float) and not float(v).is_integer() else f"{int(v)}")
                lines.append(f"| {s} | " + " | ".join(cells) + " |")
            lines.append("")
        lines += ["### PRODUCT COUNTS (FULL / COMPRESSED / THUMBNAIL / METADATA-ONLY / none)", "",
                  "| strategy | " + " | ".join(f"{x * 100:g}%" for x in budgets) + " |", "|---|" + "---|" * len(budgets)]
        for s in STRATS:
            cells = []
            for f in budgets:
                c = R.get(f"{key(s, mode)}@{f}", {}).get("counts", {})
                cells.append(" / ".join(f"{c.get(t, 0):.0f}" for t in ("FULL", "COMPRESSED", "THUMBNAIL", "METADATA", "NONE")))
            lines.append(f"| {s} | " + " | ".join(cells) + " |")
        lines.append("")
    (run / "tables.md").write_text("\n".join(lines))
    figs = run / "figures"
    figs.mkdir(exist_ok=True)
    for m, lab in (("scene_clusters_usable", "unique scene clusters at ≥ COMPRESSED"), ("unique_acquisitions_with_image", "acquisitions with any image")):
        fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
        for ax, mode in zip(axes, ("policy", "ordering")):
            for s in STRATS:
                ax.plot([f * 100 for f in budgets], [R.get(f"{key(s, mode)}@{f}", {}).get(m) for f in budgets], marker="o", label=s)
            ax.set_xscale("log")
            ax.set_title(f"{mode}")
            ax.set_xlabel("downlink budget, % of Σ FULL bytes")
        axes[0].set_ylabel(lab)
        axes[1].legend(fontsize=7)
        fig.suptitle(f"Phase 3 development baseline — {lab} (Navcam sols 412–430)")
        fig.tight_layout()
        fig.savefig(figs / f"{m}.png", dpi=130)
        plt.close(fig)
    print(f"→ {(run / 'tables.md').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
