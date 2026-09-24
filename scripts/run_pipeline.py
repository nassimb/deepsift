#!/usr/bin/env python3
"""Run the full pipeline once, record it in the audit log, and print measured stage timings."""

from __future__ import annotations

import collections

from deepsift.audit.log import AuditLog
from deepsift.core.config import load_config
from deepsift.pipeline import Pipeline


def main() -> None:
    cfg = load_config()
    r = Pipeline(cfg, audit=AuditLog()).run(sols=list(range(232, 252)), note="cli")
    md = r.metadata
    print(f"run {r.run_id} · {md['short_name']} · {md['data_source']} · sols {md['sols'][0]}–{md['sols'][-1]} · engine {r.engine['name']}")
    print("counts:", md["counts"])
    print("stage timings (ms, measured):", {k: round(v, 1) for k, v in r.timings_ms.items()})
    print("performance:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.performance.items()})
    print("gates:", dict(collections.Counter(e.gate.value for e in r.events)))
    print("final actions:", r.simulation["totals"]["final_actions"])
    t = r.simulation["totals"]
    print(f"raw {t['raw_generated']:,} B → downlinked {t['downlinked']:,} B (reduction {t['data_reduction']:.2%})")


if __name__ == "__main__":
    main()
