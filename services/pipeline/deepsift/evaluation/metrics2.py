"""Phase-2 metrics: strict / tolerant / coverage recall, precision lower bound, bytes, latency.

Definitions (also in docs/research-methodology.md):
  strict hit     a retained unit of the label's instrument overlaps [start, end]
                 (computed only for labels whose time bounds carry a documented uncertainty)
  tolerant hit   overlap with [start − δ_before, end + δ_after]; δ from the ground-truth source
  coverage       raw bytes of the label's instrument windows inside [start, end] that are covered by a
                 retained unit ÷ raw bytes of all such windows — penalises "one lucky window" on long events
  precision (lb) retained units overlapping any label (tolerant) ÷ retained units — a LOWER bound, since
                 unlabeled real phenomena exist
  no_data        no window of the label's instrument overlaps it (PDS gap) → excluded from recall
"""

from __future__ import annotations

import math
import statistics
from bisect import bisect_left, bisect_right
from datetime import timedelta

import numpy as np
import polars as pl

from deepsift.core.models import DownlinkAction
from deepsift.evaluation.labels import SEVERITY_WEIGHT, Label

STRICT_OK = {"documented_uncertainty"}


def percentiles(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0}
    a = np.asarray(xs, dtype=float)
    return {"n": int(a.size), "p50": float(np.percentile(a, 50)), "p90": float(np.percentile(a, 90)),
            "p95": float(np.percentile(a, 95)), "p99": float(np.percentile(a, 99)), "max": float(a.max()),
            "mean": float(a.mean())}


def mean_ci(xs: list[float], z: float = 1.96) -> dict:
    xs = [x for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    if not xs:
        return {"mean": None, "std": None, "ci95": None, "n": 0}
    m = statistics.fmean(xs)
    sd = statistics.stdev(xs) if len(xs) > 1 else 0.0
    half = z * sd / math.sqrt(len(xs)) if len(xs) > 1 else 0.0
    return {"mean": m, "std": sd, "ci95": [m - half, m + half], "n": len(xs)}


class WindowIndex:
    """Instrument windows (eval sols) with raw bytes, for coverage computation."""

    def __init__(self, iw: pl.DataFrame):
        self.by_inst: dict[str, tuple[list, list, list]] = {}
        for inst, part in iw.sort("t_start").group_by("instrument"):
            mids = [a + (b - a) / 2 for a, b in zip(part["t_start"], part["t_end"])]
            self.by_inst[inst[0]] = (mids, part["raw"].fill_null(0).to_list(), part["t_start"].to_list())

    def in_range(self, inst: str, t0, t1) -> list[int]:
        mids = self.by_inst.get(inst, ([], [], []))[0]
        return list(range(bisect_left(mids, t0), bisect_right(mids, t1)))


def evaluate_selection(selection, labels: list[Label], label_meta: dict[str, dict], windows: WindowIndex,
                       raw_total: int, fidelity: dict[str, float]) -> dict:
    kept = [(u, a, s) for u, a, s in selection if a != DownlinkAction.DISCARD]
    downlinked = sum(s for _, _, s in kept)
    kept_by_inst: dict[str, list] = {}
    for u, a, s in kept:
        kept_by_inst.setdefault(u.instrument, []).append((u.t0, u.t1, fidelity[a.value]))
    covered_units = set()
    per_label = {}
    for lab in labels:
        m = label_meta.get(lab.id, {})
        inst = lab.instrument
        widx = windows.in_range(inst, lab.t_start, lab.t_end)
        if not widx:
            per_label[lab.id] = {"status": "no_data", "severity": lab.severity, "subtype": m.get("subtype"), "source": lab.source.value}
            continue
        tb, ta = timedelta(seconds=m.get("tolerance_before_s", 0)), timedelta(seconds=m.get("tolerance_after_s", 0))
        strict = tol = False
        best_f = 0.0
        for u, a, s in kept:
            if u.instrument != inst:
                continue
            if u.t0 <= lab.t_end and u.t1 >= lab.t_start:
                strict = True
                covered_units.add(u.id)
                best_f = max(best_f, fidelity[a.value])
            if u.t0 <= lab.t_end + ta and u.t1 >= lab.t_start - tb:
                tol = True
                covered_units.add(u.id)
                best_f = max(best_f, fidelity[a.value])
        mids, raws, _ = windows.by_inst[inst]
        tot = sum(raws[i] for i in widx) or 1
        cov = 0
        spans = kept_by_inst.get(inst, [])
        for i in widx:
            if any(a <= mids[i] <= b for a, b, _ in spans):
                cov += raws[i]
        conf = m.get("confidence")
        per_label[lab.id] = {
            "status": "scored", "severity": lab.severity, "subtype": m.get("subtype"), "source": lab.source.value,
            "confidence": conf, "strict_hit": strict if conf in STRICT_OK else None, "tolerant_hit": tol,
            "coverage": cov / tot, "best_fidelity": best_f, "magnitude": m.get("magnitude", {}),
            "bucket": m.get("bucket"),
        }

    def rate(pred, key):
        xs = [v[key] for v in per_label.values() if v["status"] == "scored" and pred(v) and v.get(key) is not None]
        return (sum(bool(x) for x in xs) / len(xs), len(xs)) if xs else (None, 0)

    def mean_of(pred, key):
        xs = [v[key] for v in per_label.values() if v["status"] == "scored" and pred(v)]
        return statistics.fmean(xs) if xs else None

    allp = lambda v: True  # noqa: E731
    high = lambda v: v["severity"] == "high"  # noqa: E731
    value = sum(SEVERITY_WEIGHT.get(v["severity"], 1.0) * v["best_fidelity"] for v in per_label.values() if v["status"] == "scored")
    retained_n = len(kept)
    tp_units = len(covered_units)
    out = {
        "labels_scored": sum(1 for v in per_label.values() if v["status"] == "scored"),
        "labels_no_data": sum(1 for v in per_label.values() if v["status"] == "no_data"),
        "strict_recall": rate(allp, "strict_hit")[0], "strict_n": rate(allp, "strict_hit")[1],
        "tolerant_recall": rate(allp, "tolerant_hit")[0], "tolerant_n": rate(allp, "tolerant_hit")[1],
        "high_strict_recall": rate(high, "strict_hit")[0], "high_tolerant_recall": rate(high, "tolerant_hit")[0],
        "high_n": rate(high, "tolerant_hit")[1],
        "coverage": mean_of(allp, "coverage"), "high_coverage": mean_of(high, "coverage"),
        "retained_units": retained_n, "true_positive_units": tp_units, "false_positive_units": retained_n - tp_units,
        "precision_lower_bound": tp_units / retained_n if retained_n else None,
        "downlink_bytes": downlinked, "raw_bytes": raw_total,
        "data_reduction": 1 - downlinked / raw_total if raw_total else None,
        "labeled_value_proxy": value,
        "value_per_mb_proxy": value / (downlinked / 1e6) if downlinked else None,
        "actions": {a.value: sum(1 for _, x, _ in selection if x == a) for a in DownlinkAction},
        "per_label": per_label,
    }
    by_group: dict[str, dict] = {}
    for key in ("subtype", "bucket", "severity"):
        vals = sorted({v.get(key) for v in per_label.values() if v["status"] == "scored" and v.get(key) is not None})
        for g in vals:
            pred = lambda v, g=g, key=key: v.get(key) == g  # noqa: E731
            by_group[f"{key}={g}"] = {"tolerant_recall": rate(pred, "tolerant_hit")[0], "strict_recall": rate(pred, "strict_hit")[0],
                                      "coverage": mean_of(pred, "coverage"), "n": rate(pred, "tolerant_hit")[1]}
    out["by_group"] = by_group
    return out


def ece(confidences: list[float], correct: list[bool], bins: int = 10) -> dict:
    """Expected calibration error with equal-width bins, plus the reliability table."""
    if not confidences:
        return {"ece": None, "n": 0, "bins": []}
    c = np.asarray(confidences, dtype=float)
    y = np.asarray(correct, dtype=float)
    edges = np.linspace(0, 1, bins + 1)
    table, e = [], 0.0
    for i in range(bins):
        mask = (c >= edges[i]) & (c < edges[i + 1] if i < bins - 1 else c <= edges[i + 1])
        if not mask.any():
            table.append({"lo": float(edges[i]), "hi": float(edges[i + 1]), "n": 0, "mean_conf": None, "accuracy": None})
            continue
        mc, acc = float(c[mask].mean()), float(y[mask].mean())
        e += mask.sum() / len(c) * abs(mc - acc)
        table.append({"lo": float(edges[i]), "hi": float(edges[i + 1]), "n": int(mask.sum()), "mean_conf": mc, "accuracy": acc})
    return {"ece": float(e), "n": int(len(c)), "bins": table, "overall_accuracy": float(y.mean()), "mean_confidence": float(c.mean())}


def pareto_front(points: list[dict], maximize: list[str], minimize: list[str]) -> list[int]:
    idx = []
    for i, p in enumerate(points):
        dominated = False
        for j, q in enumerate(points):
            if i == j:
                continue
            ge = all((q[k] or 0) >= (p[k] or 0) for k in maximize) and all((q[k] or 0) <= (p[k] or 0) for k in minimize)
            gt = any((q[k] or 0) > (p[k] or 0) for k in maximize) or any((q[k] or 0) < (p[k] or 0) for k in minimize)
            if ge and gt:
                dominated = True
                break
        if not dominated:
            idx.append(i)
    return idx
