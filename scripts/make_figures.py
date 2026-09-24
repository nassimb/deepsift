#!/usr/bin/env python3
"""Research figures from stored study runs → artifacts/figures/<run_id>/*.png (+ .csv of plotted data).

Only reads artifacts/runs/<run_id>/results.json and rows.jsonl. Never hard-codes numbers. A figure
whose data does not exist (e.g. cost without real Jev calls) is not drawn; a NOT_GENERATED.txt line
records why.

    uv run python scripts/make_figures.py <run_id> [<run_id> ...]
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# Okabe–Ito colour-blind-safe palette + distinct markers/line styles (identity never by colour alone)
PALETTE = ["#000000", "#E69F00", "#56B4E9", "#009E73", "#0072B2", "#D55E00", "#CC79A7", "#999999", "#F0E442"]
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*", "h"]
STYLE = {"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.alpha": 0.25,
         "figure.dpi": 150, "savefig.bbox": "tight", "legend.frameon": False}


def label_of(s: str) -> str:
    return s.replace("/", " · ").replace("_", " ")


def get(v, k):
    x = v.get(k) if v else None
    return x["mean"] if isinstance(x, dict) else x


def ci(v, k):
    x = v.get(k) if v else None
    return x.get("ci95") if isinstance(x, dict) else None


def order(strategies):
    pref = ["ORACLE — NOT DEPLOYABLE", "RANDOM", "STATISTICAL", "RULES", "RULES_PLUS_STATISTICAL", "LOCAL_EDGE"]
    return [s for s in pref if s in strategies] + sorted(s for s in strategies if s not in pref)


def write_csv(path: Path, header, rows):
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def budget_curves(res, out: Path, key: str, ylabel: str, fname: str, notes: list[str]):
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    rows = []
    for ax, ds in zip(axes, ("real", "synthetic")):
        curves = res.get(f"{ds}_curves", {})
        for i, s in enumerate(order(curves)):
            pts = sorted((float(f), v) for f, v in curves[s].items())
            xs = [f * 100 for f, v in pts if get(v, key) is not None]
            ys = [get(v, key) for f, v in pts if get(v, key) is not None]
            if not xs:
                continue
            ls = ":" if s.startswith("ORACLE") else "-"
            ax.plot(xs, ys, ls, color=PALETTE[i % 9], marker=MARKERS[i % 9], ms=4, lw=1.4, label=label_of(s))
            if s == "RANDOM":
                lo = [ci(v, key)[0] for f, v in pts if ci(v, key)]
                hi = [ci(v, key)[1] for f, v in pts if ci(v, key)]
                if len(lo) == len(xs):
                    ax.fill_between(xs, lo, hi, color=PALETTE[i % 9], alpha=0.12, lw=0)
            rows += [[ds, s, x, y] for x, y in zip(xs, ys)]
        ax.set_xscale("log")
        ax.set_xlabel("downlink budget (% of generated raw bytes, log)")
        n = next((get(v, "labels") for c in curves.values() for v in c.values() if get(v, "labels")), None)
        ax.set_title(f"{'DOCUMENTED EVENTS' if ds == 'real' else 'SYNTHETIC STRESS TEST'} · {res['split']} · n={n:.0f}" if n else ds)
    axes[0].set_ylabel(ylabel)
    axes[1].legend(fontsize=7, loc="lower right")
    fig.suptitle(f"{ylabel} vs downlink budget — run {res['run_id']}", fontsize=10)
    fig.savefig(out / f"{fname}.png")
    plt.close(fig)
    write_csv(out / f"{fname}.csv", ["dataset", "strategy", "budget_percent", key], rows)


def storage_curve(res, out: Path, notes):
    st = res.get("storage") or []
    if not st:
        notes.append("recall_vs_storage: no storage rows")
        return
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    rows = []
    for ax, ds in zip(axes, ("real", "synthetic")):
        sub = [r for r in st if r["dataset"] == ds]
        combos = sorted({(r["strategy"], r["policy"]) for r in sub})
        for i, (s, pol) in enumerate(combos):
            caps = sorted({r["storage_bytes"] for r in sub})
            ys = []
            for c in caps:
                rs = [r for r in sub if r["strategy"] == s and r["policy"] == pol and r["storage_bytes"] == c]
                hl = sum(r["high_labels"] for r in rs)
                ys.append(sum(r["high_preserved"] for r in rs) / hl if hl else np.nan)
            ax.plot([c / 1024 for c in caps], ys, "-" if pol.startswith("PROTECTED") else "--", marker=MARKERS[i % 9], ms=4,
                    color=PALETTE[(i // 2) % 9], label=f"{label_of(s)} · {pol.replace('_', ' ').lower()}")
            rows += [[ds, s, pol, c, y] for c, y in zip(caps, ys)]
        ax.set_xscale("log")
        ax.set_xlabel("onboard storage during full-segment blackout (KiB, log)")
        ax.set_title("DOCUMENTED EVENTS" if ds == "real" else "SYNTHETIC STRESS TEST")
    axes[0].set_ylabel("high-severity events with ≥1 product preserved")
    axes[1].legend(fontsize=6.5, loc="lower right")
    fig.suptitle(f"Preservation vs storage capacity, two storage policies — run {res['run_id']}", fontsize=10)
    fig.savefig(out / "recall_vs_storage.png")
    plt.close(fig)
    write_csv(out / "recall_vs_storage.csv", ["dataset", "strategy", "policy", "storage_bytes", "high_preserved_fraction"], rows)


def bytes_by_strategy(res, out: Path, notes):
    ref = res.get("synthetic_reference") or {}
    ss = [s for s in order(ref) if ref[s]]
    if not ss:
        notes.append("bytes_by_strategy: no reference rows")
        return
    vals = [get(ref[s], "downlink_bytes") / 1e6 for s in ss]
    fig, ax = plt.subplots(figsize=(7, 0.35 * len(ss) + 1))
    ax.barh(range(len(ss)), vals, color="#56B4E9", height=0.6)
    ax.set_yticks(range(len(ss)), [label_of(s) for s in ss], fontsize=7.5)
    for i, v in enumerate(vals):
        ax.text(v, i, f" {v:.2f} MB", va="center", fontsize=7)
    ax.set_xlabel("downlinked MB (synthetic stress test, all batches, reference budget)")
    ax.invert_yaxis()
    fig.savefig(out / "bytes_by_strategy.png")
    plt.close(fig)
    write_csv(out / "bytes_by_strategy.csv", ["strategy", "downlink_mb"], list(zip(ss, vals)))


def latency(res, out: Path, notes):
    lat = res.get("latency") or {}
    keys = [k for k in lat if lat[k].get("n")]
    if not keys:
        notes.append("latency_distribution: no latency data")
        return
    fig, ax = plt.subplots(figsize=(8, 0.4 * len(keys) + 1.2))
    for i, k in enumerate(keys):
        v = lat[k]
        ax.plot([v["p50"], v["p90"], v["p95"], v["p99"], v["max"]], [i] * 5, "|", color="#000000", ms=10)
        ax.hlines(i, v["p50"], v["p99"], color="#0072B2", lw=3)
        ax.text(v["max"], i, f"  p50 {v['p50']:.3g} · p99 {v['p99']:.3g} · max {v['max']:.3g} ms (n={v['n']})", va="center", fontsize=6.5)
    ax.set_yticks(range(len(keys)), [k.replace("_", " ") for k in keys], fontsize=7)
    ax.set_xscale("log")
    ax.set_xlabel("milliseconds (log) — bar p50→p99, ticks p50/p90/p95/p99/max; measured on the development laptop")
    fig.savefig(out / "latency_distribution.png")
    plt.close(fig)
    write_csv(out / "latency_distribution.csv", ["series", "n", "p50", "p90", "p95", "p99", "max"],
              [[k, lat[k]["n"], lat[k]["p50"], lat[k]["p90"], lat[k]["p95"], lat[k]["p99"], lat[k]["max"]] for k in keys])


def calibration(res, out: Path, notes):
    cal = {k: v for k, v in (res.get("calibration") or {}).items() if v.get("n")}
    if not cal:
        notes.append("calibration: no engine confidences")
        return
    ks = sorted(cal)
    fig, axes = plt.subplots(1, len(ks), figsize=(3.2 * len(ks), 3.4), squeeze=False)
    rows = []
    for ax, k in zip(axes[0], ks):
        b = [x for x in cal[k]["bins"] if x["n"]]
        ax.plot([0, 1], [0, 1], ":", color="#999999", lw=1)
        ax.plot([x["mean_conf"] for x in b], [x["accuracy"] for x in b], "o-", color="#D55E00", ms=4)
        for x in b:
            ax.annotate(str(x["n"]), (x["mean_conf"], x["accuracy"]), fontsize=6, xytext=(3, -8), textcoords="offset points")
        mock = ":MOCK:" in k
        ax.set_title(f"{k}\nECE {cal[k]['ece']:.3f} · n={cal[k]['n']}" + ("\n(MOCK HEURISTIC — not Jev)" if mock else ""), fontsize=7)
        ax.set_xlabel("MODEL CONFIDENCE")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        rows += [[k, x["lo"], x["hi"], x["n"], x["mean_conf"], x["accuracy"]] for x in b]
    axes[0][0].set_ylabel("observed agreement with labels")
    fig.suptitle("Reliability of MODEL CONFIDENCE (not probability of scientific truth)", fontsize=9)
    fig.savefig(out / "confidence_calibration.png")
    plt.close(fig)
    write_csv(out / "confidence_calibration.csv", ["series", "bin_lo", "bin_hi", "n", "mean_confidence", "accuracy"], rows)


def difficulty(res, out: Path, notes):
    g = res.get("synthetic_by_group") or {}
    buckets = ["NEAR_NOISE_FLOOR", "WEAK", "MODERATE", "OBVIOUS", "QUALITY_FAULT"]
    ss = [s for s in order(g) if any(f"bucket={b}" in g[s] for b in buckets)]
    if not ss:
        notes.append("difficulty: no bucket rows")
        return
    fig, ax = plt.subplots(figsize=(9, 3.6))
    w = 0.8 / len(ss)
    rows = []
    for i, s in enumerate(ss):
        ys = [g[s].get(f"bucket={b}", {}).get("tolerant_recall", np.nan) for b in buckets]
        ax.bar(np.arange(len(buckets)) + i * w, ys, w, color=PALETTE[i % 9], label=label_of(s),
               hatch="//" if s.startswith("ORACLE") else None)
        rows += [[s, b, y, g[s].get(f"bucket={b}", {}).get("n")] for b, y in zip(buckets, ys)]
    ax.set_xticks(np.arange(len(buckets)) + 0.4 - w / 2, [b.replace("_", " ") for b in buckets], fontsize=8)
    ax.set_ylabel("tolerant recall (reference budget)")
    ax.set_title(f"Synthetic stress test by difficulty bucket (σ of local background) — run {res['run_id']}", fontsize=9)
    ax.legend(fontsize=6.5, ncol=3)
    fig.savefig(out / "performance_by_difficulty.png")
    plt.close(fig)
    write_csv(out / "performance_by_difficulty.csv", ["strategy", "bucket", "tolerant_recall", "n"], rows)


def real_vs_synth(res, out: Path, notes):
    r, s = res.get("real_reference") or {}, res.get("synthetic_reference") or {}
    ss = [x for x in order(set(r) | set(s)) if (r.get(x) or s.get(x))]
    if not ss:
        return
    fig, axes = plt.subplots(1, 2, figsize=(10, 0.35 * len(ss) + 1.4), sharey=True)
    rows = []
    for ax, key, title in ((axes[0], "tolerant_recall", "tolerant recall"), (axes[1], "coverage", "coverage of event data")):
        a = [get(r.get(x), key) or 0 for x in ss]
        b = [get(s.get(x), key) or 0 for x in ss]
        y = np.arange(len(ss))
        ax.barh(y - 0.2, a, 0.38, color="#0072B2", label="documented events")
        ax.barh(y + 0.2, b, 0.38, color="#E69F00", label="synthetic stress test", hatch="..")
        ax.set_title(title, fontsize=9)
        rows += [[x, key, ra, sb] for x, ra, sb in zip(ss, a, b)]
    axes[0].set_yticks(range(len(ss)), [label_of(x) for x in ss], fontsize=7)
    axes[0].invert_yaxis()
    axes[1].legend(fontsize=7)
    fig.suptitle(f"Documented-event vs synthetic performance at the reference budget (never pooled) — run {res['run_id']}", fontsize=9)
    fig.savefig(out / "real_vs_synthetic.png")
    plt.close(fig)
    write_csv(out / "real_vs_synthetic.csv", ["strategy", "metric", "documented", "synthetic"], rows)


def cost_vs_recall(res, out: Path, notes):
    u = res.get("jev_usage") or {}
    if not u.get("calls"):
        notes.append("cost_vs_recall: NOT GENERATED — no real Jev calls in this run (cost cannot be measured without the API)")
        return
    ref = res.get("synthetic_reference") or {}
    jev = [s for s in ref if s.startswith("JEV_")]
    fig, ax = plt.subplots(figsize=(6, 3.6))
    per_call = u["cost_usd"] / u["calls"]
    for i, s in enumerate(jev):
        ax.scatter(per_call * 1000, get(ref[s], "high_tolerant_recall"), color=PALETTE[i % 9], marker=MARKERS[i % 9], label=label_of(s))
    ax.set_xlabel("measured cost per 1,000 events (USD, configured price × reported input tokens)")
    ax.set_ylabel("high-severity recall (synthetic)")
    ax.legend(fontsize=6.5)
    fig.savefig(out / "cost_vs_recall.png")
    plt.close(fig)


def main() -> None:
    for run_id in sys.argv[1:]:
        res = json.loads((ROOT / "artifacts" / "runs" / run_id / "results.json").read_text())
        out = ROOT / "artifacts" / "figures" / run_id
        out.mkdir(parents=True, exist_ok=True)
        notes: list[str] = []
        plt.rcParams.update(STYLE)
        budget_curves(res, out, "tolerant_recall", "event recall (tolerant)", "recall_vs_budget", notes)
        budget_curves(res, out, "high_tolerant_recall", "high-severity recall (tolerant)", "high_recall_vs_budget", notes)
        budget_curves(res, out, "coverage", "coverage of labelled event data", "coverage_vs_budget", notes)
        budget_curves(res, out, "value_per_mb_proxy", "labelled value per MB (PROXY)", "value_proxy_vs_budget", notes)
        storage_curve(res, out, notes)
        bytes_by_strategy(res, out, notes)
        latency(res, out, notes)
        calibration(res, out, notes)
        difficulty(res, out, notes)
        real_vs_synth(res, out, notes)
        cost_vs_recall(res, out, notes)
        notes.append("deep_model_calls_avoided: NOT GENERATED — deep escalation is disabled in Phase 2 (no Anthropic spend)")
        (out / "NOT_GENERATED.txt").write_text("\n".join(notes) + "\n")
        print(f"{run_id}: {len(list(out.glob('*.png')))} figures → {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
