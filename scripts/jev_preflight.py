#!/usr/bin/env python3
"""Show exactly what a Jev run would cost BEFORE anything is sent. Makes no API call.

    uv run python scripts/jev_preflight.py --mode smoke
    uv run python scripts/jev_preflight.py --mode pilot
    uv run python scripts/jev_preflight.py --mode validation [--variants a,b] [--batches 25]
    uv run python scripts/jev_preflight.py --mode test          # frozen configuration(s) only

Limits: JEV_MAX_CALLS (default 1000), JEV_MAX_COST_USD (default 1.00).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "pipeline"))

from deepsift.core.config import load_config  # noqa: E402
from deepsift.core.env import load_dotenv  # noqa: E402
from deepsift.decision.jev import VARIANTS, jev_available  # noqa: E402
from deepsift.decision.jev_cache import JevCache  # noqa: E402
from deepsift.evaluation.jev_plan import build_plan, fmt_summary, guard, limits_from_env  # noqa: E402


def frozen_variants(cfg) -> list[str]:
    sel = (cfg.provenance or {}).get("jev_selection") or {}
    if not sel.get("frozen"):
        raise SystemExit("no frozen Jev selection in config/phase2.yaml — the test preflight is only defined after "
                         "docs/jev-model-selection.md has been written and frozen on VALIDATION")
    return [sel["primary_variant"]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=["smoke", "pilot", "validation", "test"])
    ap.add_argument("--variants", default=None)
    ap.add_argument("--batches", type=int, default=25)
    ap.add_argument("--n", type=int, default=None, help="sample size for smoke/pilot")
    ap.add_argument("--allow-calls", type=int, default=None)
    ap.add_argument("--allow-cost", type=float, default=None)
    args = ap.parse_args()
    load_dotenv()
    cfg = load_config(ROOT / "config" / "phase2.yaml")
    if args.mode == "test":
        variants = frozen_variants(cfg)
    elif args.variants:
        variants = args.variants.split(",")
    else:
        variants = ["no_mission_objective"] if args.mode == "smoke" else list(VARIANTS)
    plan, _ = build_plan(cfg, args.mode, variants, batches=args.batches, n_sample=args.n)
    s = plan.summary(JevCache())
    max_calls, max_cost = limits_from_env()
    ok, why = guard(s, max_calls, max_cost, args.allow_calls, args.allow_cost)
    print(fmt_summary(s))
    if plan.funnel:
        print("FUNNEL (real data, scored sols):")
        for f in plan.funnel:
            print(f"  {f['segment']}: {f['raw_samples']:,} samples → {f['instrument_windows']:,} windows → "
                  f"{f['candidate_windows']:,} candidate windows → {f['candidate_events']:,} candidate events → Jev evaluations")
    print(f"GUARD                   {'OK' if ok else 'BLOCKED'} — {why}")
    print(f"API KEY                 {'present' if jev_available() else 'ABSENT — nothing can be sent'}")
    out = ROOT / "artifacts" / "jev_preflight" / f"preflight_{args.mode}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({**s, "guard_ok": ok, "guard_reason": why, "limits": {"JEV_MAX_CALLS": max_calls, "JEV_MAX_COST_USD": max_cost}}, indent=1))
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
