"""Plan Jev work before spending anything: exact events, exact payloads, cache hits, cost, time.

Modes
  smoke       ~30 diverse VALIDATION events, one variant — verifies API, schema, parsing, cache, logging
  pilot       ~300 stratified VALIDATION events × all five variants — development diagnostics only
  validation  every scored VALIDATION candidate (real + synthetic batches) × chosen variants
  test        every scored TEST candidate × the FROZEN configuration(s) only

Pricing source (checked 2026-09-25): https://docs.typesafe.ai/models.md — "Jev 1.13 · jev-1.13.0 · Price
(per Btok / per Mtok) $42 / $0.042 · Charged per input token. Output tokens are free. · Rate limits
250,000 tokens per second / 1,200 requests per minute" (page warns limits adjust dynamically).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
from dataclasses import dataclass, field

from deepsift.core.config import Config
from deepsift.decision.jev import ALL_VARIANTS, TRANSPORT, question_specs_for, questions_payload, sdk_version
from deepsift.decision.jev_cache import JevCache, request_key
from deepsift.decision.state import build_state_variant
from deepsift.evaluation.segments import eval_filter_events, load_segment, segments
from deepsift.evaluation.sweeps import plan_sweep_batch
from deepsift.features.detect import detect_events
from deepsift.features.novelty import assign_novelty
from deepsift.objectives.objective import load_objectives
from deepsift.priority.engine import rules_type

PRICING = {"model": "typesafe/jev-1.13", "transport": TRANSPORT, "provider": "TypeSafe",
           "usd_per_mtok_input": 0.042, "usd_per_mtok_output": 0.0,
           "requests_per_minute": 1200, "tokens_per_second": 250_000,
           "source": "https://openrouter.ai/api/v1/models/typesafe/jev-1.13/endpoints", "retrieved": "2026-09-25",
           "verbatim": 'endpoint "TypeSafe | typesafe/jev-1.13-20260917": pricing {"prompt":"0.000000042","completion":"0"}',
           "rate_limit_source": "TypeSafe direct (docs.typesafe.ai/models.md); OpenRouter's own limit for this key is not published — used only for the time estimate",
           "actual_cost": "each OpenRouter response carries usage.cost (USD); the run budget uses it when present"}
CHARS_PER_TOKEN_ASSUMED = 4.0            # used only until the cache holds real usage; reported as an assumption
VENDOR_LATENCY_MS = (70, 500)            # TypeSafe-stated range; replaced by measured p50 once available
MISSION = ("MSL / CURIOSITY", "Gale Crater, Mars (4.59°S, 137.44°E landing site)")


def limits_from_env() -> tuple[int, float]:
    return int(os.environ.get("JEV_MAX_CALLS", "1000")), float(os.environ.get("JEV_MAX_COST_USD", "1.00"))


@dataclass
class PlannedRequest:
    key: str
    event_id: str
    variant: str
    chars: int
    dataset: str
    segment: str
    batch: int | None


@dataclass
class Plan:
    mode: str
    split: str
    variants: list[str]
    model: str
    events_by_dataset: dict[str, int] = field(default_factory=dict)
    requests: list[PlannedRequest] = field(default_factory=list)
    funnel: list[dict] = field(default_factory=list)

    def summary(self, cache: JevCache | None) -> dict:
        cached = cache.keys() if cache else set()
        uniq: dict[str, PlannedRequest] = {}
        for r in self.requests:
            uniq.setdefault(r.key, r)
        live = [r for k, r in uniq.items() if k not in cached]
        st = cache.stats() if cache else {}
        cpt = st.get("measured_chars_per_token") or CHARS_PER_TOKEN_ASSUMED
        tokens = sum(r.chars for r in live) / cpt
        cost = tokens / 1e6 * PRICING["usd_per_mtok_input"]
        rpm_bound_min = len(live) / PRICING["requests_per_minute"]
        lat = st.get("latency_p50_ms")
        conc = 8
        lat_bound_min = [len(live) * x / 1000 / conc / 60 for x in ((lat, lat) if lat else VENDOR_LATENCY_MS)]
        return {
            "mode": self.mode, "split": self.split, "variants": self.variants, "model": self.model,
            "candidate_events": self.events_by_dataset,
            "requests_without_cache": len(self.requests),
            "unique_requests": len(uniq),
            "already_cached": len(uniq) - len(live),
            "live_calls_needed": len(live),
            "live_calls_by_variant": {v: sum(1 for r in live if r.variant == v) for v in self.variants},
            "requests_per_event": 1,
            "decisions_per_request": {v: len(question_specs_for(v)) for v in self.variants},
            "estimated_input_tokens": round(tokens),
            "token_estimate_basis": (f"measured {cpt:.2f} chars/token from {st.get('entries')} cached calls" if st.get("measured_chars_per_token")
                                     else f"ASSUMED {CHARS_PER_TOKEN_ASSUMED} chars/token (no real usage yet) — treat cost as ±50 %"),
            "estimated_cost_usd": round(cost, 4),
            "pricing": PRICING,
            "estimated_minutes": {"rate_limit_floor": round(rpm_bound_min, 1),
                                  "latency_bound_range": [round(x, 1) for x in lat_bound_min],
                                  "basis": "measured p50" if lat else "vendor-stated 70–500 ms, 8 concurrent"},
            "funnel": self.funnel,
        }


def _payload(e, variant, objective) -> tuple[str, int, dict]:
    sv = ALL_VARIANTS[variant][0]
    state = build_state_variant(e, *MISSION, sv, objective)
    q = questions_payload(question_specs_for(variant))
    return state, len(json.dumps(state, ensure_ascii=False)) + len(json.dumps(q, ensure_ascii=False)), q


def _candidate_sets(cfg: Config, split: str, batches: int):
    """Yield (dataset, segment, batch, events, injections) exactly as the study produces them."""
    for seg in segments(split):
        sd = load_segment(seg, cfg.detection.rems_window_s, cfg.compression.decimation_factor, cfg.compression.zlib_level)
        det0 = detect_events(sd.mission, sd.adapter, cfg)
        assign_novelty(det0.events)
        ev0 = eval_filter_events(det0.events, sd)
        yield "real", sd, det0, None, ev0, [], seg
        seed0 = int(hashlib.sha256(f"{split}:{seg.id}".encode()).hexdigest()[:8], 16) % 1_000_000
        n = max(10, int(0.8 * (seg.eval[1] - seg.eval[0] + 1)))
        for b in range(batches):
            inj = plan_sweep_batch(sd.mission.samples, det0.windows, seg.eval, n, seed0 + b, cfg.detection.min_sigma or {}, f"{seg.id}-B{b:02d}")
            det = detect_events(sd.mission, sd.adapter, cfg, injections=inj)
            assign_novelty(det.events)
            yield "synthetic", sd, det, b, eval_filter_events(det.events, sd), inj, seg


def score_tier(e, cfg: Config | None) -> str:
    """Detector score relative to the frozen level threshold of the event's instrument."""
    thr = (cfg.detection.rad_z_threshold if e.instrument == "RAD" else cfg.detection.z_threshold) if cfg else 9.0
    r = e.features.deviation_score / thr
    return "below_level_threshold" if r < 1 else "near_threshold" if r < 1.5 else "medium" if r < 3 else "high"


def _stratum(e, inj_by_id, cfg: Config | None = None) -> tuple:
    """(label status, synthetic severity, instrument, detector-score tier, rules type)."""
    ids = e.synthetic_injection_ids
    inj = inj_by_id.get(ids[0]) if ids else None
    status = "synthetic" if ids else "unlabelled"
    sev = (inj.severity if inj else "?") if ids else "none"
    return (status, sev, e.instrument, score_tier(e, cfg), rules_type(e))


def stratified_sample(events_with_inj, n: int, seed: int, cfg: Config | None = None) -> list:
    """Round-robin over strata so every (label status, severity, instrument, score tier, rules type) cell is represented."""
    rng = random.Random(seed)
    cells: dict[tuple, list] = {}
    for e, inj_by_id, tag in events_with_inj:
        cells.setdefault(_stratum(e, inj_by_id, cfg), []).append((e, tag))
    for v in cells.values():
        rng.shuffle(v)
    keys = sorted(cells)
    out, seen = [], set()
    while len(out) < n and any(cells[k] for k in keys):
        for k in keys:
            if cells[k] and len(out) < n:
                e, tag = cells[k].pop()
                sig = (e.id, tag)
                if sig not in seen:
                    seen.add(sig)
                    out.append((e, tag, k))
    return out


def build_plan(cfg: Config, mode: str, variants: list[str], batches: int = 25, n_sample: int | None = None,
               split: str | None = None, seed: int = 20260925) -> tuple[Plan, list]:
    split = split or ("test" if mode == "test" else "validation")
    objective = load_objectives()[cfg.objective].model_dump(mode="json")
    plan = Plan(mode=mode, split=split, variants=variants, model=cfg.decision_engine.jev_model)
    selected: list = []
    if mode in ("smoke", "pilot"):
        pool = []
        for dataset, sd, det, b, evs, inj, seg in _candidate_sets(cfg, split, batches=1):
            inj_by_id = {i.id: i for i in inj}
            pool += [(e, inj_by_id, f"{seg.id}:{dataset}:{b}") for e in evs]
        n = n_sample or (30 if mode == "smoke" else 300)
        selected = stratified_sample(pool, n, seed, cfg)
        plan.events_by_dataset = {"sampled": len(selected)}
        for e, tag, stratum in selected:
            for v in variants:
                state, chars, q = _payload(e, v, objective)
                plan.requests.append(PlannedRequest(request_key(state, q, v, plan.model, sdk_version(), TRANSPORT), e.id, v, chars,
                                                    tag.split(":")[1], tag.split(":")[0], None))
        return plan, selected
    for dataset, sd, det, b, evs, inj, seg in _candidate_sets(cfg, split, batches):
        plan.events_by_dataset[dataset] = plan.events_by_dataset.get(dataset, 0) + len(evs)
        if dataset == "real":
            iw = det.instrument_windows.filter((det.instrument_windows["sol"] >= seg.eval[0]) & (det.instrument_windows["sol"] <= seg.eval[1]))
            smp = sd.mission.samples.filter((sd.mission.samples["sol"] >= seg.eval[0]) & (sd.mission.samples["sol"] <= seg.eval[1]))
            plan.funnel.append({"segment": seg.id, "raw_samples": smp.height, "instrument_windows": iw.height,
                                "candidate_windows": int(iw["flagged"].sum()), "candidate_events": len(evs)})
        for e in evs:
            for v in variants:
                state, chars, q = _payload(e, v, objective)
                plan.requests.append(PlannedRequest(request_key(state, q, v, plan.model, sdk_version(), TRANSPORT), e.id, v, chars, dataset, seg.id, b))
    return plan, selected


def guard(summary: dict, max_calls: int, max_cost: float, allow_calls: int | None, allow_cost: float | None) -> tuple[bool, str]:
    """Abort unless planned live calls/cost fit the limits, or an explicit override covers them exactly."""
    calls, cost = summary["live_calls_needed"], summary["estimated_cost_usd"]
    lim_calls = allow_calls if allow_calls is not None else max_calls
    lim_cost = allow_cost if allow_cost is not None else max_cost
    if "ASSUMED" in summary["token_estimate_basis"] and allow_cost is None and calls > 200:
        return False, ("token usage not yet measured (cost is an assumption); run the smoke test first or pass an explicit "
                       "--allow-cost for this run")
    if calls > lim_calls:
        return False, f"planned live calls {calls:,} > limit {lim_calls:,} (JEV_MAX_CALLS or --allow-calls)"
    if cost > lim_cost:
        return False, f"estimated cost ${cost:.4f} > limit ${lim_cost:.2f} (JEV_MAX_COST_USD or --allow-cost)"
    return True, f"within limits: {calls:,} live calls ≤ {lim_calls:,}; ${cost:.4f} ≤ ${lim_cost:.2f}"


def fmt_summary(s: dict) -> str:
    lines = [
        f"MODE {s['mode'].upper()} · SPLIT {s['split'].upper()} · model {s['model']} · variants {', '.join(s['variants'])}",
        f"CANDIDATE EVENTS        {json.dumps(s['candidate_events'])}",
        f"REQUESTS WITHOUT CACHE  {s['requests_without_cache']:,}",
        f"UNIQUE REQUESTS         {s['unique_requests']:,}   (1 request per event per variant; decisions/request {s['decisions_per_request']})",
        f"ALREADY CACHED          {s['already_cached']:,}",
        f"LIVE CALLS NEEDED       {s['live_calls_needed']:,}   {s['live_calls_by_variant']}",
        f"ESTIMATED INPUT TOKENS  {s['estimated_input_tokens']:,}   [{s['token_estimate_basis']}]",
        f"ESTIMATED COST          ${s['estimated_cost_usd']:.4f}   (@ ${s['pricing']['usd_per_mtok_input']}/Mtok input, output free — {s['pricing']['source']}, retrieved {s['pricing']['retrieved']})",
        f"ESTIMATED TIME          ≥ {s['estimated_minutes']['rate_limit_floor']} min (1,200 req/min limit); "
        f"{s['estimated_minutes']['latency_bound_range'][0]}–{s['estimated_minutes']['latency_bound_range'][1]} min by latency ({s['estimated_minutes']['basis']})",
    ]
    return "\n".join(lines)


__all__ = ["PRICING", "Plan", "build_plan", "guard", "fmt_summary", "limits_from_env", "stratified_sample", "math"]
