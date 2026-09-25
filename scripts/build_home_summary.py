#!/usr/bin/env python3
"""Build the homepage's lightweight data snapshot: apps/web/data/home-summary.json.

    uv run python scripts/build_home_summary.py

Reads ONLY existing artifacts and re-runs the same Mission Control replay the API boots (calibration segment,
config/default.yaml, mock engine — no API calls). Nothing in the pipeline, the stored runs or the audit log changes.
Every number on the homepage comes from this file or from the live API; the file records where each block came from.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "pipeline"))

from deepsift.core.config import load_config  # noqa: E402
from deepsift.core.models import DownlinkAction  # noqa: E402
from deepsift.evaluation.segments import segments  # noqa: E402
from deepsift.pipeline import Pipeline  # noqa: E402
from deepsift.simulation.scheduler import Blackout  # noqa: E402

TEST_RUN = "20260924T204836-test-c6f9"
V3_RUN = "20260925T094903-jev-v3-pilot-84af"
OUT = ROOT / "apps" / "web" / "data" / "home-summary.json"
STRATS = ["RULES", "STATISTICAL", "RULES_PLUS_STATISTICAL", "LOCAL_EDGE", "RANDOM", "ORACLE — NOT DEPLOYABLE"]
SOL_S = 88775.244


def git() -> dict:
    run = lambda *a: subprocess.run(a, cwd=ROOT, capture_output=True, text=True).stdout.strip()  # noqa: E731
    return {"commit": run("git", "rev-parse", "--short", "HEAD"), "dirty": bool(run("git", "status", "--porcelain"))}


def replay_block(cfg) -> dict:
    """The exact Mission Control replay (calibration segment), plus one blackout at the /blackout page defaults."""
    seg = segments("calibration")[0]
    sols = list(range(seg.eval[0], seg.eval[1] + 1))
    p = Pipeline(cfg)
    r = p.run(sols=sols, note="homepage snapshot")
    det = r.detection
    raw_total = int(det.instrument_windows["raw"].sum() or 0)
    cand_windows = int(det.instrument_windows["flagged"].sum())
    acts = defaultdict(int)
    for e in r.events:
        acts[(e.final_action or DownlinkAction.DISCARD).value] += 1
    tot = r.simulation["totals"]
    passes = cfg.downlink.passes_per_sol * len(sols)
    s = det.samples
    t0, t1 = s["t"].min(), s["t"].max()

    events = [[e.id, e.instrument, round(e.sol_start, 4), round(e.sol_end, 4),
               (e.decision.answers["event_type"].choice if e.decision and "event_type" in e.decision.answers else None),
               (e.final_action or DownlinkAction.DISCARD).value, round(e.priority.utility, 3) if e.priority else None]
              for e in sorted(r.events, key=lambda x: x.sol_start)]

    # blackout at the /blackout page defaults (start = first sol + 8.5, duration and storage from config)
    b = Blackout(start=sols[0] + 8.5, duration=cfg.blackout.duration_sols, storage_bytes=cfg.blackout.storage_bytes)
    sim = p.simulate([e.model_copy(deep=True) for e in r.events], det, b)
    bw = sim["blackout_window"]
    tl = [x for x in sim["timeline"] if bw["start"] - 0.25 <= x["t"] <= bw["end"] + 0.5]
    step = max(1, len(tl) // 120)
    timeline = [[round(x["t"], 4), x["storage_used"], x["capacity"], x["raw_generated"], x["downlinked"], bool(x["blackout"])] for x in tl[::step]]
    in_bo = [x for x in sim["timeline"] if x["blackout"]]
    raw_rate = (in_bo[-1]["raw_generated"] - in_bo[0]["raw_generated"]) / ((in_bo[-1]["t"] - in_bo[0]["t"]) * SOL_S) if len(in_bo) > 1 else None
    by_id = {e.id: e for e in r.events}
    during = [i for i in sim["items"] if i["kind"] == "event" and bw["start"] <= i["arrival"] < bw["end"]]
    examples = {}
    for act in ("full_data", "compress", "summary_only", "discard"):
        c = sorted([i for i in during if i["final"] == act], key=lambda i: -i["utility"])
        if c:
            i, e = c[0], by_id[c[0]["id"]]
            examples[act] = {"id": i["id"], "instrument": e.instrument, "sensors": e.sensors,
                             "event_type": e.decision.answers["event_type"].choice if e.decision else None,
                             "proposed": i["proposed"], "final": i["final"], "state": i["state"], "utility": round(i["utility"], 3),
                             "bytes": i["bytes"], "raw": i["raw"], "count_with_this_action": len(c)}
    blackout = {"start_sol": bw["start"], "end_sol": bw["end"], "duration_sols": cfg.blackout.duration_sols,
                "duration_hours": cfg.blackout.duration_sols * SOL_S / 3600, "storage_bytes": bw["storage_bytes"],
                "incoming_raw_bytes_per_s": raw_rate, "report": sim["blackout"], "timeline": timeline,
                "timeline_columns": ["sol", "storage_used", "capacity", "raw_generated", "downlinked", "blackout"],
                "events_during": len(during), "examples": examples,
                "actions_during": {a: sum(1 for i in during if i["final"] == a) for a in ("full_data", "compress", "summary_only", "discard")}}

    # one real event card: highest-utility FULL_DATA event of the replay (its stored explanation, no generated text)
    full = sorted([e for e in r.events if e.final_action == DownlinkAction.FULL_DATA and e.priority], key=lambda e: -e.priority.utility)
    e = full[0]
    pb = e.priority
    ch = {k: c for k, c in e.features.channels.items() if k in e.sensors}
    top = max(ch.values(), key=lambda c: abs(c.robust_z))
    card = {"id": e.id, "instrument": e.instrument, "sol": e.sol, "t_start": e.timestamp_start, "t_end": e.timestamp_end,
            "sensors": e.sensors, "top_channel": top.channel, "top_unit": top.unit, "robust_z": round(top.robust_z, 2),
            "duration_s": e.features.duration_s, "rarity": e.features.rarity_score, "novelty": e.features.novelty,
            "correlated_channels": e.features.correlated_channels,
            "science_value": e.decision.answers["science_value"].choice if e.decision else None,
            "event_type": e.decision.answers["event_type"].choice if e.decision else None,
            "gate": e.gate.value if e.gate else None, "proposed": e.proposed_action.value, "final": e.final_action.value,
            "priority": pb.model_dump(mode="json"), "explanation": e.explanation, "trigger_reasons": e.features.trigger_reasons,
            "bytes": e.bytes.model_dump(), "engine": r.engine, "objective": r.objective.name, "config_version": cfg.version(),
            "products": e.source.products}

    tm = r.timings_ms
    audit = [
        {"stage": "RAW DATA", "in": f"{len(r.metadata['products'])} PDS products", "out": f"{s.height:,} channel samples", "ms": tm.get("normalize")},
        {"stage": "FEATURE EXTRACTION", "in": f"{s.height:,} samples", "out": f"{det.windows.height:,} channel windows",
         "ms": (tm.get("windowing") or 0) + (tm.get("feature_extraction") or 0)},
        {"stage": "CANDIDATE DETECTION", "in": f"{det.instrument_windows.height:,} instrument windows", "out": f"{cand_windows:,} flagged → {len(r.events)} events",
         "ms": (tm.get("candidate_detection") or 0) + (tm.get("novelty") or 0)},
        {"stage": "DECISION ENGINE", "in": f"{len(r.events)} candidate events", "out": "bounded answers per event", "ms": tm.get("decision_engine"),
         "note": f"{r.engine['name']}{'' if r.engine.get('is_real_model') else ' (heuristic stand-in, not Jev)'}"},
        {"stage": "PRIORITY SCORE", "in": "answers + features + objective", "out": "utility ∈ [0, 1] per event", "ms": tm.get("priority") or tm.get("scoring")},
        {"stage": "DOWNLINK ACTION", "in": "utility, bytes, passes, storage", "out": " · ".join(f"{k} {v}" for k, v in sorted(acts.items())),
         "ms": sim.get("wall_ms")},
    ]
    return {"source": "Mission Control replay re-run with config/default.yaml (same as the API boot)",
            "segment": seg.id, "sols": [sols[0], sols[-1]], "utc": [str(t0), str(t1)], "data_source": r.metadata["data_source"],
            "products": len(r.metadata["products"]), "samples": s.height, "channel_windows": det.windows.height,
            "instrument_windows": det.instrument_windows.height, "candidate_windows": cand_windows, "events": len(r.events),
            "raw_bytes": raw_total, "downlink_capacity_bytes": passes * cfg.downlink.pass_bytes,
            "downlink": {"passes_per_sol": cfg.downlink.passes_per_sol, "pass_bytes": cfg.downlink.pass_bytes, "passes": passes},
            "downlinked_bytes": tot.get("downlinked_bytes") if isinstance(tot, dict) else None, "simulation_totals": tot,
            "final_actions": dict(acts), "engine": r.engine, "objective": r.objective.name, "config_version": cfg.version(),
            "timings_ms": tm, "event_rows": events, "event_columns": ["id", "instrument", "sol_start", "sol_end", "event_type", "final_action", "utility"],
            "blackout": blackout, "event_card": card, "audit_flow": audit}


def benchmark_block() -> dict:
    run = ROOT / "artifacts" / "runs" / TEST_RUN
    res = json.loads((run / "results.json").read_text())
    man = json.loads((run / "manifest.json").read_text())
    agg = defaultdict(lambda: {"rows": 0, "down": 0, "raw": 0, "actions": defaultdict(int), "hi": 0, "hi_any": 0, "hi_full": 0,
                               "ret": 0, "tp": 0})
    seeds = defaultdict(set)
    with (run / "rows.jsonl").open() as fh:
        for line in fh:
            row = json.loads(line)
            s = row.get("strategy")
            if s not in STRATS or "budget_fraction" not in row:      # other row types (storage, gating) are skipped
                continue
            k = (row["dataset"], s, row["budget_fraction"])
            a = agg[k]
            seeds[k].add(row.get("seed"))
            a["rows"] += 1
            a["down"] += row["downlink_bytes"]
            a["raw"] += row["raw_bytes"]
            a["ret"] += row["retained_units"]
            a["tp"] += row["true_positive_units"] if "true_positive_units" in row else row["retained_units"] - row["false_positive_units"]
            for act, n in (row.get("actions") or {}).items():
                a["actions"][act] += n
            for lab in row["per_label"].values():
                if lab.get("status") == "scored" and lab.get("severity") == "high":
                    a["hi"] += 1
                    a["hi_any"] += bool(lab.get("tolerant_hit"))
                    a["hi_full"] += bool(lab.get("tolerant_hit")) and lab.get("best_fidelity", 0) >= 1.0
    out = defaultdict(dict)
    for (ds, s, f), a in agg.items():
        n = max(1, len(seeds[(ds, s, f)]))
        out[f"{ds}|{s}"][str(f)] = {"high_labels": a["hi"] // n, "high_any": a["hi_any"] / a["hi"] if a["hi"] else None,
                                   "high_full": a["hi_full"] / a["hi"] if a["hi"] else None,
                                   "downlink_bytes": a["down"] / n, "raw_bytes": a["raw"] / n,
                                   "precision_lower_bound": a["tp"] / a["ret"] if a["ret"] else None,
                                   "actions": {k: v / n for k, v in a["actions"].items()}}
    lat = res["latency"]
    latency = {"RULES": lat.get("routing_ms_per_event:RULES", {}).get("p50"), "LOCAL_EDGE": lat.get("routing_ms_per_event:LOCAL_EDGE", {}).get("p50"),
               "priority_only": lat.get("priority_ms_per_event", {}).get("p50"), "preprocessing": lat.get("preprocessing_ms_per_event", {}).get("p50")}
    by_group = {s: {k: v for k, v in res["synthetic_by_group"].get(s, {}).items() if k.startswith("bucket=")} for s in ("RULES", "LOCAL_EDGE", "STATISTICAL")}
    real_sub = {s: {k: v for k, v in res["real_by_group"].get(s, {}).items() if k.startswith("subtype=")} for s in ("RULES", "RULES_PLUS_STATISTICAL", "RANDOM")}
    storage = [x for x in res["storage"] if x["dataset"] == "synthetic" and x["storage_bytes"] == 1048576]
    st = defaultdict(lambda: [0, 0])
    for x in storage:
        st[(x["strategy"], x["policy"])][0] += x["high_preserved"]
        st[(x["strategy"], x["policy"])][1] += x["high_labels"]
    return {"run_id": TEST_RUN, "split": "test", "note": "held-out test, evaluated once with the frozen configuration",
            "segments": man["segments"], "budgets": man["budgets"]["fractions_of_generated_raw_bytes"],
            "curves": out, "latency_p50_ms": latency, "synthetic_by_bucket_at_0.5pct": by_group, "real_by_subtype_at_0.5pct": real_sub,
            "storage_1mib_high_preserved": {f"{a}|{b}": v for (a, b), v in st.items()},
            "jev_status_in_this_run": res["jev_status"], "local_edge_footprint": res["local_edge_footprint"],
            "local_edge_model": {"features": len(res["local_edge_footprint"].get("coefficients", {})),
                                 "file_bytes": (ROOT / "artifacts" / "models" / "local_edge.json").stat().st_size},
            "git": man["git"], "config_version": man["config_version"]}


def jev_block() -> dict:
    a = json.loads((ROOT / "artifacts" / "runs" / V3_RUN / "analysis.json").read_text())
    ops = a["operations"]
    au = a["auroc"]
    pick = lambda k: {"diff": au[k]["diff"], "ci95": au[k]["ci95_cluster_bootstrap"]}  # noqa: E731
    order = {}
    for name in ("RULES", "RULES_PLUS_STATISTICAL", "LOCAL_EDGE", "JEV_V3_NO_OBJECTIVE", "JEV_V3_WITH_OBJECTIVE", "RANDOM_ORDER"):
        order[name] = {f: a["ranking"].get(f"synthetic|high|ORDER:{name}|{f}", {}).get("retention_any_fidelity") for f in (0.001, 0.0025, 0.005, 0.01)}
    return {"run_id": V3_RUN, "split": "validation", "stage": "validation pilot (not run on the held-out test)",
            "model": "typesafe/jev-1.13", "transport": "OpenRouter (remote)", "events": a["preflight"]["events"],
            "high_labels": a["ranking"]["synthetic|high|ORDER:RULES|0.005"]["labels"],
            "live_calls": ops["live_requests"], "cost_usd": ops["cost_usd"], "cost_per_1k_requests_usd": ops["cost_usd"] / ops["live_requests"] * 1000,
            "latency_ms": ops["latency_ms"], "auroc": {k: au[f"synthetic|{k}"]["auroc"] for k in ("RULES", "LOCAL_EDGE", "JEV_V3_NO_OBJECTIVE", "JEV_V3_WITH_OBJECTIVE")},
            "auroc_diff_vs_rules": {"no_objective": pick("synthetic|JEV_V3_NO_OBJECTIVE-minus-RULES"), "with_objective": pick("synthetic|JEV_V3_WITH_OBJECTIVE-minus-RULES")},
            "ordering_only_retention": order,
            "outcome": "No measurable improvement in candidate ordering over rules (validation pilot). Recommendation recorded: STOP JEV for the ranking role; decision pending."}


def data_block() -> dict:
    splits = json.loads((ROOT / "data" / "splits" / "splits.json").read_text())["splits"]
    # sol → UTC from the RAD product names themselves (RAD_RDR_<year>_<doy>_<hh>_<mm>_<sol>_...)
    pairs = []
    for f in (ROOT / "data" / "raw" / "rad").glob("RAD_RDR_*"):
        m = re.match(r"RAD_RDR_(\d{4})_(\d{3})_(\d{2})_(\d{2})_(\d{4})", f.name)
        if m:
            y, doy, hh, mm, sol = map(int, m.groups())
            pairs.append((sol, datetime(y, 1, 1, hh, mm, tzinfo=timezone.utc) + timedelta(days=doy - 1)))
    sols = sorted(pairs)

    def utc(sol: int) -> str | None:
        if not sols:
            return None
        s0, d0 = min(sols, key=lambda p: abs(p[0] - sol))
        return (d0 + timedelta(seconds=(sol - s0) * SOL_S)).date().isoformat()
    pre = json.loads((ROOT / "artifacts" / "jev_preflight" / "preflight_validation.json").read_text())
    fun = pre.get("funnel", [])
    man = json.loads((ROOT / "artifacts" / "runs" / TEST_RUN / "manifest.json").read_text())
    rp = man["datasets"].get("raw_products", {}) if isinstance(man["datasets"], dict) else {}
    out = {"splits": {}, "validation_funnel": {
        "segments": [f["segment"] for f in fun], "raw_samples": sum(f["raw_samples"] for f in fun),
        "instrument_windows": sum(f["instrument_windows"] for f in fun), "candidate_windows": sum(f["candidate_windows"] for f in fun),
        "candidate_events": sum(f["candidate_events"] for f in fun), "source": "artifacts/jev_preflight/preflight_validation.json"},
        "test_raw_products": {"files": rp.get("files"), "sha256": rp.get("digest")},
        "rad_products_on_disk": len(pairs), "rems_products_on_disk": len(list((ROOT / "data" / "raw" / "rems").glob("*")))}
    for name, sp in splits.items():
        out["splits"][name] = [{"id": s["id"], "sols": s["eval"], "utc": [utc(s["eval"][0]), utc(s["eval"][1])]} for s in sp["segments"]]
    return out


def main() -> int:
    cfg = load_config()
    summary = {"generated_at": datetime.now(timezone.utc).isoformat(), "git": git(),
               "provenance": "scripts/build_home_summary.py — measured values only; see each block's source/run_id",
               "replay": replay_block(cfg), "benchmark": benchmark_block(), "jev": jev_block(), "data": data_block()}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, separators=(",", ":"), default=str))
    print(f"→ {OUT.relative_to(ROOT)} · {OUT.stat().st_size / 1024:.1f} KiB · replay events {summary['replay']['events']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
