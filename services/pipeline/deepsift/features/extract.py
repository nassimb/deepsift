"""Windowing + statistical feature extraction (mission-agnostic).

Each (instrument, channel, window) gets level, variability and quality statistics, then is
compared to a *same-local-time* baseline built from the preceding sols. Mars surface
temperature swings ~80 K per sol and pressure ~±5 % — without a diurnal baseline, every
afternoon would look anomalous.
"""

from __future__ import annotations

import bisect

import numpy as np
import polars as pl

from deepsift.adapters.base import ChannelSpec

MAD_TO_SIGMA = 1.4826
DIP_ROLLING_SAMPLES = 61  # ~60 s at 1 Hz


def window_stats(samples: pl.DataFrame, window_expr_by_instrument: dict[str, pl.Expr], lmst_bin_minutes: int) -> pl.DataFrame:
    frames = []
    for instrument, key in window_expr_by_instrument.items():
        s = samples.filter(pl.col("instrument") == instrument)
        if s.is_empty():
            continue
        s = s.sort("channel", "t").with_columns(
            key.alias("window"),
            pl.col("t").dt.epoch("ms").cast(pl.Float64).truediv(1000).alias("ts"),
        )
        # 60-sample running median per channel; dip = how far a sample falls below it
        s = s.with_columns(
            (pl.col("value").rolling_median(DIP_ROLLING_SAMPLES, min_samples=15, center=True).over("channel") - pl.col("value"))
            .alias("below_median")
        )
        agg = s.group_by("instrument", "channel", "window").agg(
            pl.len().alias("n"),
            pl.col("t").min().alias("t_start"),
            pl.col("t").max().alias("t_end"),
            pl.col("sol").first().alias("sol"),
            pl.col("lmst_s").first().alias("lmst_s"),
            pl.col("lmst_s").mean().alias("lmst_mid"),
            pl.col("value").mean().alias("mean"),
            pl.col("value").std().alias("std"),
            pl.col("value").min().alias("min"),
            pl.col("value").max().alias("max"),
            (pl.cov("ts", "value") / pl.col("ts").var()).alias("slope"),
            pl.col("value").diff().std().alias("diff_std"),
            (pl.col("value").diff() == 0).mean().alias("flat_fraction"),
            pl.col("below_median").max().alias("dip"),
            pl.col("product").first().alias("product"),
        )
        frames.append(agg)
    w = pl.concat(frames, how="vertical_relaxed")
    # complete (window × channel) grid: a channel that vanished from a window must show up as
    # missing_fraction = 1, not as an absent row
    iwin = w.group_by("instrument", "window").agg(
        pl.col("n").max().alias("records"), pl.col("t_start").min(), pl.col("t_end").max(),
        pl.col("sol").first(), pl.col("lmst_s").min(), pl.col("lmst_mid").mean(), pl.col("product").first(),
    )
    chans = w.select("instrument", "channel").unique()
    grid = iwin.join(chans, on="instrument")
    present = w.select("instrument", "channel", "window")
    absent = grid.join(present, on=["instrument", "channel", "window"], how="anti").with_columns(pl.lit(0, dtype=pl.UInt32).alias("n"))
    w = pl.concat([w, absent.select([c for c in absent.columns if c != "records"])], how="diagonal_relaxed")
    rec = iwin.select("instrument", "window", "records")
    w = w.join(rec, on=["instrument", "window"]).with_columns(
        (1 - pl.col("n") / pl.col("records")).alias("missing_fraction"),
        (pl.col("lmst_s") // (lmst_bin_minutes * 60)).cast(pl.Int32).alias("lmst_bin"),
    )
    return w.sort("instrument", "channel", "t_start")


def add_baselines(w: pl.DataFrame, channels: list[ChannelSpec], baseline_sols: int, match_tolerance_s: int = 600) -> pl.DataFrame:
    """Attach baseline statistics from the preceding `baseline_sols` sols.

    Diurnal channels: for each prior sol, take the window whose mean local time is nearest to
    this window's (within `match_tolerance_s`), then median/MAD across those sols. This keeps the
    steep morning pressure/temperature ramps from masquerading as anomalies.
    Non-diurnal channels (RAD dose): all windows of the prior sols.
    Falls back to a leave-one-sol-out baseline over the whole segment when fewer than three
    prior sols match (start of the segment); flagged `baseline_mode = "bootstrap"`.
    """
    spec = {c.name: c for c in channels}
    diurnal = [c.name for c in channels if c.diurnal]
    keys = ["instrument", "channel", "window"]
    ref = w.select(
        "channel", pl.col("sol").alias("ref_sol"), pl.col("lmst_mid").alias("ref_lmst"), pl.col("mean").alias("ref_mean"),
        pl.col("diff_std").alias("ref_diff_std"), pl.col("flat_fraction").alias("ref_flat"),
        pl.col("missing_fraction").alias("ref_missing"),
    ).sort("ref_lmst")
    sols = sorted(w["sol"].unique().to_list())
    target = w.select(*keys, "sol", "lmst_mid")

    def pairs(offsets_fn) -> pl.DataFrame:
        rows = [(s, r) for s in sols for r in offsets_fn(s) if r in sols]
        return pl.DataFrame(rows, schema={"sol": pl.Int32, "ref_sol": pl.Int32}, orient="row")

    def matched(pair_df: pl.DataFrame) -> pl.DataFrame:
        t = target.join(pair_df, on="sol")
        d = t.filter(pl.col("channel").is_in(diurnal)).sort("channel", "ref_sol", "lmst_mid").join_asof(
            ref.filter(pl.col("channel").is_in(diurnal)), left_on="lmst_mid", right_on="ref_lmst",
            by=["channel", "ref_sol"], strategy="nearest", tolerance=float(match_tolerance_s), check_sortedness=False,
        ).filter(pl.col("ref_mean").is_not_null())
        nd = t.filter(~pl.col("channel").is_in(diurnal)).join(ref, on=["channel", "ref_sol"])
        return pl.concat([d, nd.select(d.columns)])

    def summarize(frame: pl.DataFrame, mode: str) -> pl.DataFrame:
        return frame.group_by(keys).agg(
            pl.col("ref_mean").median().alias("baseline"),
            (pl.col("ref_mean") - pl.col("ref_mean").median()).abs().median().alias("baseline_mad"),
            pl.col("ref_diff_std").median().alias("baseline_diff_std"),
            pl.col("ref_flat").median().alias("baseline_flat"),
            pl.col("ref_missing").median().alias("baseline_missing"),
            pl.col("ref_sol").n_unique().alias("baseline_n"),
            pl.lit(mode).alias("baseline_mode"),
        )

    trailing = summarize(matched(pairs(lambda s: range(s - baseline_sols, s))), "trailing").filter(pl.col("baseline_n") >= 3)
    loo = summarize(matched(pairs(lambda s: [r for r in sols if r != s])), "bootstrap")
    base = pl.concat([trailing, loo.join(trailing.select(keys), on=keys, how="anti")])
    w = w.join(base, on=keys, how="left").with_columns(
        pl.when(pl.col("baseline_n").fill_null(0) < 3).then(pl.lit("insufficient")).otherwise(pl.col("baseline_mode")).alias("baseline_mode")
    )

    min_sigma = pl.col("channel").replace_strict({k: v.min_sigma for k, v in spec.items()}, default=0.1)
    sigma = pl.max_horizontal(pl.col("baseline_mad").fill_null(0) * MAD_TO_SIGMA, min_sigma)
    w = w.with_columns(
        sigma.alias("sigma"),
        pl.when(pl.col("baseline_mode") == "insufficient").then(0.0)
        .otherwise((pl.col("mean") - pl.col("baseline")) / sigma).fill_null(0.0).alias("robust_z"),
        (pl.col("diff_std") / pl.max_horizontal(pl.col("baseline_diff_std"), min_sigma * 0.2)).fill_null(1.0).alias("noise_ratio"),
        (pl.col("dip").fill_null(0.0) / min_sigma).alias("dip_sigma"),
    )
    return w


def add_rarity(w: pl.DataFrame) -> pl.DataFrame:
    """Causal rarity: fraction of *earlier* windows of the same channel with a smaller |z|."""
    out = []
    for ch, part in w.sort("t_start").group_by("channel", maintain_order=True):
        absz = np.abs(part["robust_z"].to_numpy())
        seen: list[float] = []
        r = np.zeros(len(absz))
        for i, v in enumerate(absz):
            r[i] = bisect.bisect_left(seen, v) / len(seen) if seen else 0.5
            bisect.insort(seen, v)
        out.append(part.with_columns(pl.Series("rarity", r)))
    return pl.concat(out).sort("instrument", "channel", "t_start")


def flag_windows(w: pl.DataFrame, det, channels: list[ChannelSpec]) -> pl.DataFrame:
    """Deterministic candidate filter — cheap, explainable, configurable."""
    lo = {c.name: c.physical_range[0] for c in channels}
    hi = {c.name: c.physical_range[1] for c in channels}
    zthr = pl.when(pl.col("instrument") == "RAD").then(det.rad_z_threshold).otherwise(det.z_threshold)
    enough = pl.col("n") >= det.min_samples
    return w.with_columns(
        (pl.col("robust_z").abs() >= zthr).alias("f_level"),
        ((pl.col("channel") == "pressure") & (pl.col("dip").fill_null(0) >= det.dip_threshold_pa)).alias("f_dip"),
        (enough & (pl.col("flat_fraction").fill_null(0) >= det.flat_fraction_threshold) & (pl.col("baseline_flat").fill_null(1) < 0.5)).alias("f_stuck"),
        ((pl.col("missing_fraction") >= det.missing_fraction_threshold) & (pl.col("baseline_missing").fill_null(1) < 0.1)).alias("f_dropout"),
        (enough & (pl.col("noise_ratio") >= det.noise_ratio_threshold)).alias("f_noise"),
        ((pl.col("min") < pl.col("channel").replace_strict(lo, default=-1e12)) | (pl.col("max") > pl.col("channel").replace_strict(hi, default=1e12))).alias("f_range"),
    ).with_columns(
        pl.any_horizontal("f_level", "f_dip", "f_stuck", "f_dropout", "f_noise", "f_range").alias("flagged")
    )


def reasons_for(row: dict, det) -> list[str]:
    ch, u = row["channel"], row.get("unit", "")
    out = []
    if row["f_level"]:
        thr = det.rad_z_threshold if row["instrument"] == "RAD" else det.z_threshold
        out.append(f"{ch}: mean {row['mean']:.2f} {u} is {row['robust_z']:+.1f}σ from the same-local-time baseline "
                   f"({row['baseline']:.2f}); threshold ±{thr}σ")
    if row["f_dip"]:
        out.append(f"{ch}: {row['dip']:.2f} {u} drop below the 60 s running median (threshold {det.dip_threshold_pa} {u})")
    if row["f_stuck"]:
        out.append(f"{ch}: {row['flat_fraction']:.0%} of consecutive samples identical (stuck-value threshold "
                   f"{det.flat_fraction_threshold:.0%}; baseline {row['baseline_flat']:.0%})")
    if row["f_dropout"]:
        out.append(f"{ch}: {row['missing_fraction']:.0%} of records missing this channel (baseline {row['baseline_missing']:.0%})")
    if row["f_noise"]:
        out.append(f"{ch}: sample-to-sample noise {row['noise_ratio']:.1f}× the baseline (threshold {det.noise_ratio_threshold}×)")
    if row["f_range"] and row["min"] is not None:
        out.append(f"{ch}: value outside physical range [{row['min']:.2f}, {row['max']:.2f}] {u}")
    return out
