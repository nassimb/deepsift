"""Candidate event generation: merge flagged windows into typed ScientificEvents."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import timedelta

import polars as pl

from deepsift.core.models import ByteCosts, ChannelFeatures, EventFeatures, ScientificEvent, SourceReference
from deepsift.features.extract import add_baselines, add_rarity, flag_windows, reasons_for, window_stats


@dataclass
class DetectionResult:
    events: list[ScientificEvent]
    windows: pl.DataFrame             # one row per (instrument, channel, window) with features + flags
    instrument_windows: pl.DataFrame  # one row per (instrument, window) with bytes + flagged
    samples: pl.DataFrame             # possibly injected copy
    timings_ms: dict[str, float] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)


def _iso(t) -> str:
    return t.isoformat().replace("+00:00", "Z")


def detect_events(mission, adapter, config, injections=None) -> DetectionResult:
    det = config.detection
    timings: dict[str, float] = {}
    channels = mission.metadata.channels
    units = {c.name: c.unit for c in channels}

    t0 = time.perf_counter()
    samples = mission.samples
    if injections:
        from deepsift.evaluation.injection import apply_injections

        samples = apply_injections(samples, injections, seed=config.benchmark.injection_seed)
    elif "injection_id" not in samples.columns:
        samples = samples.with_columns(pl.lit(None, dtype=pl.Utf8).alias("injection_id"))
    timings["injection"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    instruments = sorted(samples["instrument"].unique().to_list())
    w = window_stats(samples, {i: adapter.window_key(i) for i in instruments}, det.lmst_bin_minutes)
    timings["windowing"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    w = add_baselines(w, channels, det.baseline_sols)
    w = add_rarity(w)
    timings["feature_extraction"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    w = flag_windows(w, det, channels).with_columns(pl.col("channel").replace_strict(units, default="").alias("unit"))
    # injection ids per instrument window
    inj_map: dict[tuple[str, str], set[str]] = {}
    tagged = samples.filter(pl.col("injection_id").is_not_null())
    for instrument in instruments:
        part = tagged.filter(pl.col("instrument") == instrument)
        if part.is_empty():
            continue
        part = part.with_columns(adapter.window_key(instrument).alias("window"))
        for win, ids in part.group_by("window").agg(pl.col("injection_id").unique()).iter_rows():
            inj_map[(instrument, win)] = set(ids)

    iw = (
        w.group_by("instrument", "window")
        .agg(
            pl.col("t_start").min(), pl.col("t_end").max(), pl.col("sol").first(), pl.col("lmst_s").min(),
            pl.col("flagged").any(), pl.col("robust_z").abs().max().alias("max_abs_z"),
            pl.col("dip_sigma").max().alias("max_dip_sigma"), pl.col("rarity").max().alias("max_rarity"),
        )
        .join(mission.window_bytes.drop("product"), on=["instrument", "window"], how="left")
        .sort("instrument", "t_start")
    )
    iw = iw.with_columns(
        pl.struct("instrument", "window").map_elements(
            lambda r: sorted(inj_map.get((r["instrument"], r["window"]), set())), return_dtype=pl.List(pl.Utf8)
        ).alias("injection_ids")
    )

    # point-sampled instruments (one record per window, e.g. RAD integrations): a window lasts
    # until the next one starts (capped at 2 h)
    iw = iw.with_columns(
        pl.when(pl.col("t_end") == pl.col("t_start"))
        .then(pl.min_horizontal(
            pl.col("t_start").shift(-1).over("instrument").fill_null(pl.col("t_start") + timedelta(hours=1)),
            pl.col("t_start") + timedelta(hours=2),
        ))
        .otherwise(pl.col("t_end"))
        .alias("t_end"),
        pl.int_range(pl.len()).over("instrument").alias("seq"),
    )

    # merge flagged windows into events: adjacent in sequence, or closer than merge_gap_s
    events: list[ScientificEvent] = []
    flagged_iw = iw.filter(pl.col("flagged"))
    groups: list[list[dict]] = []
    for instrument in instruments:
        cur: list[dict] = []
        for r in flagged_iw.filter(pl.col("instrument") == instrument).iter_rows(named=True):
            adjacent = cur and r["seq"] == cur[-1]["seq"] + 1
            close = cur and (r["t_start"] - cur[-1]["t_end"]) <= timedelta(seconds=det.merge_gap_s)
            if cur and not (adjacent or close):
                groups.append(cur)
                cur = []
            cur.append(r)
        if cur:
            groups.append(cur)

    flagged_spans = [(g[0]["instrument"], g[0]["t_start"], g[-1]["t_end"]) for g in groups]
    coin = timedelta(seconds=det.coincidence_window_s)
    ch_rows: dict[tuple[str, str], list[dict]] = {}
    for r in w.iter_rows(named=True):
        ch_rows.setdefault((r["instrument"], r["window"]), []).append(r)

    for g in groups:
        instrument = g[0]["instrument"]
        t_start, t_end = g[0]["t_start"], g[-1]["t_end"]
        rows = [cr for gw in g for cr in ch_rows[(instrument, gw["window"])]]
        per_ch: dict[str, list[dict]] = {}
        for cr in rows:
            per_ch.setdefault(cr["channel"], []).append(cr)
        chan_feats: dict[str, ChannelFeatures] = {}
        reasons: list[str] = []
        flagged_channels: list[str] = []
        for ch, lst in per_ch.items():
            peak = max(lst, key=lambda x: abs(x["robust_z"]))
            n = sum(x["n"] for x in lst)
            have = [x for x in lst if x["n"]]
            chan_feats[ch] = ChannelFeatures(
                channel=ch, unit=units.get(ch, ""), n=n,
                mean=sum(x["mean"] * x["n"] for x in have) / max(n, 1) if have else None,
                std=max(((x["std"] or 0.0) for x in have), default=0.0),
                min=min((x["min"] for x in have), default=None), max=max((x["max"] for x in have), default=None),
                baseline=peak["baseline"], baseline_mad=peak["baseline_mad"], robust_z=peak["robust_z"],
                dip=max((x["dip"] or 0.0) for x in lst), rate_of_change=peak["slope"] or 0.0,
                flat_fraction=max((x["flat_fraction"] or 0.0) for x in lst),
                missing_fraction=max(x["missing_fraction"] for x in lst),
                noise_ratio=max(x["noise_ratio"] for x in lst), rarity=max(x["rarity"] for x in lst),
            )
            fl = [x for x in lst if x["flagged"]]
            if fl:
                flagged_channels.append(ch)
                strongest = max(fl, key=lambda x: abs(x["robust_z"]) + (x["dip_sigma"] or 0))
                reasons.extend(reasons_for(strongest, det))
        deviation = max(
            max(abs(c.robust_z) for c in chan_feats.values()),
            max((x["dip_sigma"] or 0.0) for x in rows if x["f_dip"]) if any(x["f_dip"] for x in rows) else 0.0,
        )
        roc = max(abs(c.rate_of_change) * det.rems_window_s / max((c.baseline_mad or 0) * 1.4826, 1e-3) for c in chan_feats.values())
        coincident = any(
            other != instrument and s <= t_end + coin and e >= t_start - coin for other, s, e in flagged_spans
        )
        feats = EventFeatures(
            deviation_score=round(deviation, 3),
            rarity_score=max(c.rarity for c in chan_feats.values()),
            duration_s=(t_end - t_start).total_seconds() + 1,
            rate_of_change=round(min(roc, 1e3), 3),
            correlated_channels=len(flagged_channels),
            cross_instrument_coincidence=coincident,
            lmst_hour=round(g[0]["lmst_s"] / 3600, 3),
            trigger_reasons=reasons,
            channels=chan_feats,
        )
        raw = sum(x["raw"] or 0 for x in g)
        summary_blob = json.dumps(feats.model_dump(mode="json"), separators=(",", ":"))
        products = sorted({cr["product"] for cr in rows})
        inj_ids = sorted({i for gw in g for i in gw["injection_ids"]})
        sol = int(g[0]["sol"])
        eid = f"{mission.metadata.id.split('_')[0].upper()}-{instrument}-{sol:04d}-{t_start.strftime('%H%M%S')}"
        events.append(ScientificEvent(
            id=eid, mission=mission.metadata.id, instrument=instrument, sol=sol,
            timestamp_start=_iso(t_start), timestamp_end=_iso(t_end),
            sol_start=sol + g[0]["lmst_s"] / 86400, sol_end=sol + g[0]["lmst_s"] / 86400 + (t_end - t_start).total_seconds() / 88775.244,
            sensors=flagged_channels, features=feats,
            source=SourceReference(
                instrument=instrument, products=products,
                row_start=min(x["row_start"] for x in g if x["row_start"] is not None),
                row_end=max(x["row_end"] for x in g if x["row_end"] is not None),
                data_source=mission.metadata.data_source,
            ),
            bytes=ByteCosts(
                raw=raw, full=sum(x["full"] or 0 for x in g), compressed=sum(x["compressed"] or 0 for x in g),
                summary=len(summary_blob),
            ),
            synthetic_injection_ids=inj_ids,
        ))
    timings["candidate_detection"] = (time.perf_counter() - t0) * 1000

    counts = {
        "samples": samples.height,
        "channel_windows": w.height,
        "instrument_windows": iw.height,
        "flagged_windows": flagged_iw.height,
        "events": len(events),
    }
    return DetectionResult(events=events, windows=w, instrument_windows=iw, samples=samples, timings_ms=timings, counts=counts)
