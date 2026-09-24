"""Spacecraft storage + downlink scheduler + communication blackout (discrete-event simulation).

Clock: mission local time as fractional sol (sol + LMST/24h). Model:
  * Raw instrument data is generated continuously (bytes measured from the PDS records).
  * When a candidate event completes, its triage *product* (FULL / COMPRESS / SUMMARY) enters
    onboard storage; the raw buffer is released. Non-candidate data becomes one per-sol,
    per-instrument statistical summary.
  * Storage over capacity → queued products are degraded one level at a time
    (FULL→COMPRESS→SUMMARY→DISCARD) until the new product fits: unprotected products first
    (lowest utility-per-byte first), products with utility ≥ `protect_utility` only after that.
    Every degradation is logged.
  * Relay passes transmit queued products in descending utility until the pass budget is spent;
    products may span passes (packetised).
  * During a blackout no passes occur and the (smaller) blackout storage capacity applies.
All parameters are simulation assumptions from config — not Curiosity's actual allocations.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from deepsift.core.models import ACTION_RANK, RANK_ACTION, DownlinkAction

BACKGROUND_UTILITY = 0.15


@dataclass
class Item:
    id: str
    kind: str                       # event | background
    arrival: float                  # fractional sol
    utility: float
    action: DownlinkAction
    sizes: dict[str, int]           # action value -> bytes
    raw: int
    cost_exponent: float = 0.5
    proposed: DownlinkAction | None = None
    sent: int = 0
    state: str = "pending"          # pending | queued | downlinked | discarded
    downlinked_at: float | None = None
    history: list[dict] = field(default_factory=list)

    @property
    def size(self) -> int:
        return self.sizes.get(self.action.value, 0)

    @property
    def remaining(self) -> int:
        return max(self.size - self.sent, 0)

    @property
    def density(self) -> float:
        kb = max(self.size, 1) / 1024
        return self.utility / (kb ** self.cost_exponent)


@dataclass
class Blackout:
    start: float
    duration: float
    storage_bytes: int

    @property
    def end(self) -> float:
        return self.start + self.duration

    def active(self, t: float) -> bool:
        return self.start <= t < self.end


def pass_times(sol_lo: int, sol_hi: int, passes_per_sol: int, first_hour: float = 3.5) -> list[float]:
    out = []
    for s in range(sol_lo, sol_hi + 2):
        for i in range(passes_per_sol):
            out.append(s + ((first_hour + i * 24 / passes_per_sol) % 24) / 24)
    return sorted(out)


def simulate(items: list[Item], raw_timeline: list[tuple[float, int]], cfg, blackout: Blackout | None = None,
             sol_range: tuple[int, int] | None = None) -> dict:
    dl = cfg.downlink
    protect = dl.protect_utility if dl.protect_utility is not None else cfg.priority.thresholds.full_data
    items = sorted(items, key=lambda i: i.arrival)
    lo = sol_range[0] if sol_range else int(items[0].arrival) if items else 0
    hi = sol_range[1] if sol_range else int(items[-1].arrival) if items else 0
    passes = pass_times(lo, hi, dl.passes_per_sol)
    end_t = hi + 1.0

    ev: list[tuple[float, int, str, object]] = [(i.arrival, 1, "arrival", i) for i in items]
    ev += [(p, 2, "pass", None) for p in passes if p <= end_t + 0.5]
    if blackout:
        ev += [(blackout.start, 0, "blackout_start", None), (blackout.end, 0, "blackout_end", None)]
    raw_iter = sorted(raw_timeline)
    ev.sort(key=lambda x: (x[0], x[1]))

    storage: list[Item] = []
    log: list[dict] = []
    timeline: list[dict] = []
    totals = {"raw_generated": 0, "products_generated": 0, "downlinked": 0, "degraded_bytes": 0,
              "storage_discarded_items": 0, "degradations": 0}
    ri = 0
    blackout_report: dict | None = None
    blackout_arrivals: list[Item] = []

    def capacity(t: float) -> int:
        return blackout.storage_bytes if blackout and blackout.active(t) else dl.storage_bytes

    def used() -> int:
        return sum(i.remaining for i in storage)

    def make_room(t: float, need: int) -> None:
        cap = capacity(t)
        while used() + need > cap:
            cands = [i for i in storage if i.sent == 0 and i.action != DownlinkAction.DISCARD]
            if not cands:
                break
            # protected products (utility ≥ protect threshold) are degraded only after every
            # unprotected product; within each group the lowest utility-per-byte goes first
            victim = min(cands, key=lambda i: (i.utility >= protect, i.density))
            before = victim.action
            after = RANK_ACTION[ACTION_RANK[before] - 1]
            freed = victim.size - victim.sizes.get(after.value, 0)
            victim.action = after
            totals["degradations"] += 1
            totals["degraded_bytes"] += freed
            entry = {"t": round(t, 5), "item": victim.id, "from": before.value, "to": after.value,
                     "freed": freed, "protected": victim.utility >= protect,
                     "reason": f"storage pressure ({used() + need}/{cap} B)" + (" · protected tier" if victim.utility >= protect else ""),
                     "blackout": bool(blackout and blackout.active(t))}
            victim.history.append(entry)
            log.append({"type": "degrade", **entry})
            if after == DownlinkAction.DISCARD:
                victim.state = "discarded"
                storage.remove(victim)
                totals["storage_discarded_items"] += 1

    def snapshot(t: float, kind: str) -> None:
        timeline.append({
            "t": round(t, 5), "kind": kind, "storage_used": used(), "capacity": capacity(t),
            "raw_generated": totals["raw_generated"], "downlinked": totals["downlinked"],
            "queued": len(storage), "blackout": bool(blackout and blackout.active(t)),
            "degradations": totals["degradations"],
        })

    for t, _, kind, obj in ev:
        while ri < len(raw_iter) and raw_iter[ri][0] <= t:
            totals["raw_generated"] += raw_iter[ri][1]
            ri += 1
        if kind == "arrival":
            it: Item = obj  # type: ignore[assignment]
            it.proposed = it.proposed or it.action
            if blackout and blackout.active(t):
                blackout_arrivals.append(it)
            if it.action == DownlinkAction.DISCARD:
                it.state = "discarded"
                snapshot(t, "arrival")
                continue
            # the new product competes on equal terms: add it, then degrade lowest-density products until it fits
            it.state = "queued"
            storage.append(it)
            make_room(t, 0)
            if it.state == "discarded":
                snapshot(t, "arrival")
                continue
            totals["products_generated"] += it.size
            snapshot(t, "arrival")
        elif kind == "pass":
            if blackout and blackout.active(t):
                log.append({"type": "pass_missed", "t": round(t, 5)})
                snapshot(t, "pass_missed")
                continue
            budget = dl.pass_bytes
            sent_ids = []
            for it in sorted(storage, key=lambda i: -i.utility):
                if budget <= 0:
                    break
                n = min(it.remaining, budget)
                it.sent += n
                budget -= n
                totals["downlinked"] += n
                if it.remaining == 0:
                    it.state = "downlinked"
                    it.downlinked_at = t
                    sent_ids.append(it.id)
            storage[:] = [i for i in storage if i.state == "queued"]
            log.append({"type": "pass", "t": round(t, 5), "bytes": dl.pass_bytes - budget, "completed": sent_ids})
            snapshot(t, "pass")
        elif kind == "blackout_start":
            log.append({"type": "blackout_start", "t": round(t, 5)})
            make_room(t, 0)
            snapshot(t, "blackout_start")
        elif kind == "blackout_end":
            log.append({"type": "blackout_end", "t": round(t, 5)})
            blackout_report = _blackout_report(blackout, blackout_arrivals, storage, raw_iter, cfg)
            snapshot(t, "blackout_end")

    while ri < len(raw_iter):
        totals["raw_generated"] += raw_iter[ri][1]
        ri += 1
    totals["stored_at_end"] = used()
    totals["data_reduction"] = 1 - totals["downlinked"] / totals["raw_generated"] if totals["raw_generated"] else 0.0
    by_final = {}
    for it in items:
        key = it.action.value if it.state != "discarded" else "discard"
        by_final[key] = by_final.get(key, 0) + 1
    totals["final_actions"] = by_final
    return {
        "timeline": timeline, "log": log, "totals": totals, "passes": passes,
        "items": [
            {"id": i.id, "kind": i.kind, "arrival": round(i.arrival, 5), "utility": round(i.utility, 4),
             "proposed": (i.proposed or i.action).value, "final": i.action.value if i.state != "discarded" else "discard",
             "state": i.state, "bytes": i.size if i.state != "discarded" else 0, "sent": i.sent,
             "downlinked_at": i.downlinked_at, "raw": i.raw, "history": i.history}
            for i in items
        ],
        "blackout": blackout_report,
        "blackout_window": {"start": blackout.start, "end": blackout.end, "storage_bytes": blackout.storage_bytes} if blackout else None,
    }


def _blackout_report(b: Blackout, arrivals: list[Item], storage: list[Item], raw_iter, cfg) -> dict:
    raw_in = sum(n for t, n in raw_iter if b.start <= t < b.end)
    ev = [i for i in arrivals if i.kind == "event"]
    kept = [i for i in ev if i.state == "queued"]
    thr = cfg.priority.thresholds.full_data
    important = sorted([i for i in ev if i.utility >= thr], key=lambda i: -i.utility)
    queue = sorted(storage, key=lambda i: -i.utility)
    return {
        "raw_collected": raw_in,
        "events_detected": len(ev),
        "events_retained": len(kept),
        "events_discarded": sum(1 for i in ev if i.state == "discarded"),
        "events_degraded": sum(1 for i in ev if i.history),
        "retained_bytes": sum(i.remaining for i in storage),
        "important_events": [{"id": i.id, "utility": round(i.utility, 4), "proposed": (i.proposed or i.action).value,
                              "final": i.action.value if i.state != "discarded" else "discard", "state": i.state}
                             for i in important],
        "downlink_queue": [{"id": i.id, "utility": round(i.utility, 4), "action": i.action.value, "bytes": i.remaining}
                           for i in queue[:40]],
        "pass_bytes": cfg.downlink.pass_bytes,
    }
