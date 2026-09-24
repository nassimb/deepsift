#!/usr/bin/env python3
"""Render markdown tables from a stored study run (no hand-typed numbers).

    uv run python scripts/report_tables.py <run_id> > artifacts/runs/<run_id>/tables.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def val(x):
    return x["mean"] if isinstance(x, dict) else x


def pct(x, d=0):
    x = val(x)
    return "—" if x is None else f"{100 * x:.{d}f}%"


def ci(x):
    if isinstance(x, dict) and x.get("ci95"):
        return f" [{100 * x['ci95'][0]:.0f}–{100 * x['ci95'][1]:.0f}]"
    return ""


def order(names):
    pref = ["ORACLE — NOT DEPLOYABLE", "RANDOM", "STATISTICAL", "RULES", "RULES_PLUS_STATISTICAL", "LOCAL_EDGE"]
    return [s for s in pref if s in names] + sorted(s for s in names if s not in pref)


def reference_table(res, ds):
    ref = res[f"{ds}_reference"]
    print(f"\n#### {'Documented events' if ds == 'real' else 'Synthetic stress test'} — reference budget 0.5 %\n")
    print("| strategy | labels | strict recall | tolerant recall | high-sev recall | coverage | precision (lb) | unlabelled kept | downlinked MB | value/MB (proxy) |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for s in order([k for k, v in ref.items() if v]):
        v = ref[s]
        dl = val(v.get("downlink_bytes"))
        vp = val(v.get("value_per_mb_proxy"))
        print(f"| {s} | {val(v.get('labels')):.0f} | {pct(v.get('strict_recall'))}{ci(v.get('strict_recall'))} | "
              f"{pct(v.get('tolerant_recall'))}{ci(v.get('tolerant_recall'))} | {pct(v.get('high_tolerant_recall'))}{ci(v.get('high_tolerant_recall'))} | "
              f"{pct(v.get('coverage'), 1)} | {pct(v.get('precision_lower_bound'), 1)} | {val(v.get('false_positive_units')):.0f} | "
              f"{dl / 1e6:.2f} | {'—' if vp is None else f'{vp:.1f}'} |")


def budget_table(res, ds, key):
    curves = res[f"{ds}_curves"]
    fr = sorted({float(f) for c in curves.values() for f in c})
    print(f"\n#### {key} vs budget — {ds}\n")
    print("| strategy | " + " | ".join(f"{100 * f:g}%" for f in fr) + " |")
    print("|---|" + "---|" * len(fr))
    for s in order(list(curves)):
        cells = []
        for f in fr:
            v = curves[s].get(str(f)) or curves[s].get(f) or {}
            cells.append(pct(v.get(key)))
        print(f"| {s} | " + " | ".join(cells) + " |")


def groups(res):
    g = res["synthetic_by_group"]
    buckets = ["NEAR_NOISE_FLOOR", "WEAK", "MODERATE", "OBVIOUS", "QUALITY_FAULT"]
    print("\n#### Synthetic tolerant recall by difficulty bucket (reference budget)\n")
    print("| strategy | " + " | ".join(buckets) + " |")
    print("|---|" + "---|" * len(buckets))
    for s in order(list(g)):
        print(f"| {s} | " + " | ".join(f"{pct(g[s].get(f'bucket={b}', {}).get('tolerant_recall'))} (n={g[s].get(f'bucket={b}', {}).get('n', 0)})" for b in buckets) + " |")
    rg = res["real_by_group"]
    subs = sorted({k for s in rg.values() for k in s if k.startswith("subtype=")})
    if subs:
        print("\n#### Documented events by subtype (reference budget): tolerant recall / coverage\n")
        print("| strategy | " + " | ".join(x.split("=")[1] for x in subs) + " |")
        print("|---|" + "---|" * len(subs))
        for s in order(list(rg)):
            print(f"| {s} | " + " | ".join(f"{pct(rg[s].get(x, {}).get('tolerant_recall'))} / {pct(rg[s].get(x, {}).get('coverage'), 1)} (n={rg[s].get(x, {}).get('n', 0)})" for x in subs) + " |")


def storage(res):
    st = res["storage"]
    if not st:
        return
    print("\n#### Storage sweep (whole scored segment in blackout): high-severity events preserved / products\n")
    for ds in ("real", "synthetic"):
        sub = [r for r in st if r["dataset"] == ds]
        caps = sorted({r["storage_bytes"] for r in sub})
        print(f"\n{ds}:\n")
        print("| strategy · policy | " + " | ".join(f"{c // 1024} KiB" for c in caps) + " |")
        print("|---|" + "---|" * len(caps))
        for s, pol in sorted({(r["strategy"], r["policy"]) for r in sub}):
            cells = []
            for c in caps:
                rs = [r for r in sub if r["strategy"] == s and r["policy"] == pol and r["storage_bytes"] == c]
                hl, hp = sum(r["high_labels"] for r in rs), sum(r["high_preserved"] for r in rs)
                full = sum(r["full"] for r in rs)
                summ = sum(r["summary"] for r in rs)
                cells.append(f"{hp}/{hl} · F{full} S{summ}")
            print(f"| {s} · {pol} | " + " | ".join(cells) + " |")


def calibration(res):
    print("\n#### Confidence calibration (MODEL CONFIDENCE, not probability of scientific truth)\n")
    print("| series | n | ECE | mean confidence | observed agreement |")
    print("|---|---|---|---|---|")
    for k, c in sorted(res["calibration"].items()):
        if c.get("n"):
            print(f"| {k} | {c['n']} | {c['ece']:.3f} | {pct(c.get('mean_confidence'), 1)} | {pct(c.get('overall_accuracy'), 1)} |")


def latency(res):
    print("\n#### Latency (ms, measured on the development laptop)\n")
    print("| series | n | p50 | p90 | p95 | p99 | max |")
    print("|---|---|---|---|---|---|---|")
    for k, v in sorted(res["latency"].items()):
        if v.get("n"):
            print(f"| {k} | {v['n']} | {v['p50']:.3g} | {v['p90']:.3g} | {v['p95']:.3g} | {v['p99']:.3g} | {v['max']:.3g} |")


def gating(res):
    for k, pts in res["gating"].items():
        front = [p for p in pts if p["pareto"]]
        print(f"\n#### Gating sweep {k}: Pareto-optimal points ({len(front)}/{len(pts)})\n")
        print("| auto ≥ | uncertain ≥ | high-sev recall | precision (lb) | would escalate | downlinked MB |")
        print("|---|---|---|---|---|---|")
        for p in front:
            print(f"| {p['auto']} | {p['uncertain']} | {pct(p['high_tolerant_recall'])} | {pct(p['precision_lower_bound'], 1)} | "
                  f"{p['would_escalate']}/{p['events']} | {p['downlink_bytes'] / 1e6:.2f} |")


def main():
    rid = sys.argv[1]
    res = json.loads((ROOT / "artifacts" / "runs" / rid / "results.json").read_text())
    man = json.loads((ROOT / "artifacts" / "runs" / rid / "manifest.json").read_text())
    print(f"### Run {rid} — split {res['split'].upper()} — git {man['git']['describe']} — config {man['config_version']} — Jev: {res['jev_status']}")
    for ds in ("real", "synthetic"):
        reference_table(res, ds)
    for ds in ("real", "synthetic"):
        budget_table(res, ds, "high_tolerant_recall")
        budget_table(res, ds, "coverage")
    groups(res)
    storage(res)
    gating(res)
    calibration(res)
    latency(res)
    print(f"\nJev usage: {res['jev_usage']}")


if __name__ == "__main__":
    main()
