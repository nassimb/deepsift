from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from deepsift.adapters.base import ChannelSpec
from deepsift.adapters.curiosity import CuriosityAdapter, parse_rad_product
from deepsift.core.models import DataSource
from deepsift.evaluation.injection import Injection, apply_injections
from deepsift.features.extract import add_baselines, flag_windows, window_stats


# ------------------------------------------------------------------ adapter / ingestion
def test_fixture_is_labelled_local_nasa_sample(fixture_adapter):
    md = fixture_adapter.metadata()
    assert md.data_source == DataSource.LOCAL_NASA_SAMPLE
    assert md.sols == [238, 239, 240, 241, 242, 243]


def test_normalized_schema_and_physical_ranges(fixture_adapter):
    m = fixture_adapter.normalize()
    s = m.samples
    assert set(s.columns) >= {"t", "sol", "lmst_s", "instrument", "channel", "value", "record", "product"}
    assert s["value"].is_not_null().all()
    assert (s.filter(pl.col("value") == -999.0)).is_empty(), "PDS missing constant must be filtered"
    p = s.filter(pl.col("channel") == "pressure")["value"]
    assert 700 < p.min() and p.max() < 1000, "Gale pressure should be within a few hundred Pa of ~870"
    assert s["t"].dtype == pl.Datetime("us", "UTC")


def test_rems_utc_is_monotonic_with_lmst(fixture_adapter):
    from deepsift.adapters.curiosity import sclk_sanity

    assert sclk_sanity(fixture_adapter.normalize().samples) > 0.999


def test_missing_data_raises_instead_of_substituting(tmp_path):
    a = CuriosityAdapter(raw_dir=tmp_path / "a", fixture_dir=tmp_path / "b")
    with pytest.raises(FileNotFoundError):
        a.load()


def test_rad_parser_reads_dose_blocks():
    txt = (b'[FILE]\n[OBSERVATION: 00]\nSTART_OBS_MARS="0242 10:00:00"\nSTART_OBS_UTC="2013-101 07:02:00"\n'
           b'[DOSIMETRY_TOTAL_DOSE_B: 00]\n\n12.13\n\n[DOSIMETRY_TOTAL_DOSE_E: 00]\n\n10.8\n'
           b'[OBSERVATION: 01]\nSTART_OBS_MARS="0242 11:00:00"\nSTART_OBS_UTC="2013-101 08:02:00"\n'
           b'[DOSIMETRY_TOTAL_DOSE_B: 01]\n\n9.1\n')
    df = parse_rad_product(txt, "SYNTHETIC")
    assert df.height == 2
    assert df["dose_b"].to_list() == [12.13, 9.1]
    assert df["dose_e"].to_list()[1] is None
    assert df["t"][0] == datetime(2013, 4, 11, 7, 2, tzinfo=timezone.utc)


def test_window_bytes_are_measured(fixture_adapter):
    wb = fixture_adapter.normalize().window_bytes
    assert (wb["full"] < wb["raw"]).all() and (wb["compressed"] <= wb["full"]).all()


# ------------------------------------------------------------------ features (SYNTHETIC TEST DATA)
SPECS = [ChannelSpec("pressure", "REMS", "Pa", 0.25, (300, 1300))]


def _synthetic_sols(n_sols=6, spike_sol=None, spike=0.0):
    rows = []
    for sol in range(100, 100 + n_sols):
        for k in range(600):  # 10 min of 1 Hz data at LMST 12:00
            v = 850.0 + 0.1 * ((k * 7919) % 11 - 5) / 5
            if sol == spike_sol and 300 <= k < 600:
                v += spike
            rows.append({"t": datetime(2013, 1, 1, tzinfo=timezone.utc) + timedelta(days=sol, seconds=k), "sol": sol,
                         "lmst_s": 43200.0 + k, "instrument": "REMS", "channel": "pressure", "value": v, "record": k, "product": "SYN"})
    return pl.DataFrame(rows).with_columns(pl.col("sol").cast(pl.Int32))


def _key():
    return pl.concat_str([pl.col("sol").cast(pl.Utf8), pl.lit(":"), (pl.col("lmst_s") // 300).cast(pl.Int64).cast(pl.Utf8)])


def test_window_stats_basic():
    w = window_stats(_synthetic_sols(1), {"REMS": _key()}, 30)
    assert w.height == 2 and w["n"].to_list() == [300, 300]
    assert abs(w["mean"][0] - 850.0) < 0.2


def test_baseline_and_level_flag(cfg):
    s = _synthetic_sols(6, spike_sol=105, spike=5.0)
    w = window_stats(s, {"REMS": _key()}, 30)
    w = add_baselines(w, SPECS, baseline_sols=7)
    w = flag_windows(w, cfg.detection, SPECS)
    spiked = w.filter((pl.col("sol") == 105) & (pl.col("lmst_s") >= 43500))
    assert spiked["robust_z"][0] > cfg.detection.z_threshold
    assert spiked["f_level"][0]
    assert not w.filter(pl.col("sol") < 105)["f_level"].any()


def test_first_sols_without_enough_history_do_not_flag(cfg):
    s = _synthetic_sols(2, spike_sol=100, spike=50.0)
    w = add_baselines(window_stats(s, {"REMS": _key()}, 30), SPECS, 7)
    assert (w["baseline_mode"] == "insufficient").all()
    assert (w["robust_z"] == 0).all()


def test_injection_is_tagged_and_stuck_value(cfg):
    s = _synthetic_sols(1)
    inj = Injection(id="INJ-T", kind="sensor_stuck", channels=["pressure"], t_start=s["t"][100], duration_s=60,
                    magnitude=0, expected_type="instrument_anomaly", severity="medium")
    out = apply_injections(s, [inj])
    tagged = out.filter(pl.col("injection_id") == "INJ-T")
    assert tagged.height == 61
    assert tagged["value"].n_unique() == 1
    assert out.filter(pl.col("injection_id").is_null()).height == s.height - 61


def test_dropout_injection_removes_samples(cfg):
    s = _synthetic_sols(1)
    inj = Injection(id="INJ-D", kind="sensor_dropout", channels=["pressure"], t_start=s["t"][0], duration_s=299,
                    magnitude=0, expected_type="instrument_anomaly", severity="low")
    out = apply_injections(s, [inj])
    assert out.height == s.height - 300


# ------------------------------------------------------------------ detection on real fixture
def test_detection_finds_documented_sep_on_sol_242(fixture_run):
    _, r, _ = fixture_run
    rad = [e for e in r.events if e.instrument == "RAD" and e.sol == 242]
    assert rad, "sol 242 RAD dose elevation should produce a candidate"
    assert max(e.features.channels["dose_b"].max for e in rad) > 12.0
    assert all(e.source.data_source == DataSource.LOCAL_NASA_SAMPLE for e in r.events)


def test_most_windows_are_not_candidates(fixture_run):
    _, r, _ = fixture_run
    iw = r.detection.instrument_windows
    assert iw["flagged"].mean() < 0.5
