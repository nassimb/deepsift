#!/usr/bin/env python3
"""Run the triage benchmark from the command line and print a summary table.

    npm run benchmark -- --trials 5
"""

from __future__ import annotations

import argparse

from deepsift.core.config import load_config
from deepsift.evaluation.benchmark import run_benchmark
from deepsift.pipeline import Pipeline


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=3)
    args = ap.parse_args()
    cfg = load_config()
    p = Pipeline(cfg)
    r = run_benchmark(p, cfg, trials=args.trials, sols=list(range(232, 252)))
    print(f"experiment {r['id']} · engine {r['engine']['name']} (real model: {r['engine']['is_real_model']}) · "
          f"{r['data_source']} sols {r['sols'][0]}–{r['sols'][-1]} · budget {r['budget_bytes']:,} B · {r['trials']} trials")
    print(f"{'strategy':<14}{'recall':>9}{'high':>9}{'unlabeled':>11}{'downlink':>12}{'value/MB':>10}{'deep':>6}")
    for k, v in r["summary"].items():
        if not v["available"]:
            print(f"{k:<14}  UNAVAILABLE — {v['reason']}")
            continue
        f = lambda key, fmt: fmt.format(v[key]["mean"]) if v.get(key) else "—"  # noqa: E731
        print(f"{k:<14}{f('recall', '{:.1%}'):>9}{f('recall_high', '{:.1%}'):>9}{f('retained_unlabeled_rate', '{:.1%}'):>11}"
              f"{f('downlink_bytes', '{:,.0f}'):>12}{f('science_value_per_mb_proxy', '{:.1f}'):>10}{f('deep_calls', '{:.0f}'):>6}")
    print("\ncaveats:")
    for c in r["caveats"]:
        print(" -", c)


if __name__ == "__main__":
    main()
