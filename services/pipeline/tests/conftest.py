"""Shared fixtures.

Integration tests run on data/fixtures/msl_curiosity — real PDS bytes (sols 238–243), so they
work offline and never depend on the download cache. Unit tests build small frames that are
explicitly SYNTHETIC TEST DATA.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from deepsift.adapters.curiosity import CuriosityAdapter
from deepsift.core.config import DATA_DIR, Config, load_config
from deepsift.core.models import (
    AnswerDist,
    ByteCosts,
    ChannelFeatures,
    DataSource,
    EngineDecision,
    EventFeatures,
    ScientificEvent,
    SourceReference,
)

FIXTURE = DATA_DIR / "fixtures" / "msl_curiosity"


@pytest.fixture(scope="session")
def cfg() -> Config:
    return load_config()


@pytest.fixture(scope="session")
def fixture_adapter(tmp_path_factory) -> CuriosityAdapter:
    empty_raw = tmp_path_factory.mktemp("no_raw")  # force the bundled-sample path
    a = CuriosityAdapter(raw_dir=empty_raw, fixture_dir=FIXTURE)
    a.load()
    return a


@pytest.fixture(scope="session")
def fixture_run(cfg, fixture_adapter, tmp_path_factory):
    from deepsift.audit.log import AuditLog
    from deepsift.pipeline import Pipeline

    audit = AuditLog(tmp_path_factory.mktemp("audit") / "audit.duckdb")
    p = Pipeline(cfg, adapter=fixture_adapter, audit=audit)
    r = p.run(persist=False)
    return p, r, audit


def make_event(eid="SYN-1", instrument="REMS", z=6.0, sensors=("pressure",), dip=0.0, flat=0.0, missing=0.0, noise=1.0,
               duration=300.0, novelty=0.8, raw=100_000, full=10_000, compressed=2_000, summary=800, sol=240, lmst_h=12.0,
               baseline=900.0, mean=None) -> ScientificEvent:
    """SYNTHETIC TEST DATA — a hand-built event for unit tests."""
    t0 = datetime(2013, 4, 9, 12, tzinfo=timezone.utc)
    ch = sensors[0]
    cf = ChannelFeatures(channel=ch, unit="Pa", n=300, mean=mean if mean is not None else baseline + z, std=1.0,
                         min=baseline - 5, max=baseline + 5, baseline=baseline, baseline_mad=1 / 1.4826, robust_z=z,
                         dip=dip, flat_fraction=flat, missing_fraction=missing, noise_ratio=noise, rarity=0.97)
    feats = EventFeatures(deviation_score=abs(z), rarity_score=0.97, duration_s=duration, rate_of_change=0.1,
                          correlated_channels=len(sensors), cross_instrument_coincidence=False, novelty=novelty,
                          lmst_hour=lmst_h, trigger_reasons=[f"{ch}: synthetic"], channels={ch: cf})
    return ScientificEvent(
        id=eid, mission="test", instrument=instrument, sol=sol, timestamp_start=t0.isoformat(),
        timestamp_end=(t0 + timedelta(seconds=duration)).isoformat(), sol_start=sol + lmst_h / 24,
        sol_end=sol + lmst_h / 24 + duration / 88775, sensors=list(sensors), features=feats,
        source=SourceReference(instrument=instrument, products=["SYNTHETIC"], data_source=DataSource.SYNTHETIC_TEST_DATA),
        bytes=ByteCosts(raw=raw, full=full, compressed=compressed, summary=summary),
    )


def make_decision(sci="high", sci_conf=0.95, etype="atmospheric", type_conf=0.95, action="full_data", fail_yes=0.05,
                  deep=0.1) -> EngineDecision:
    """SYNTHETIC TEST DATA — a hand-built engine decision."""
    levels = ["none", "low", "medium", "high", "critical"]
    types = ["nominal", "atmospheric", "radiation", "thermal", "instrument_anomaly", "unknown"]
    acts = ["discard", "summary_only", "compress", "full_data"]

    def dist(keys, k, conf):
        rest = (1 - conf) / (len(keys) - 1)
        return {x: (conf if x == k else rest) for x in keys}

    return EngineDecision(engine="test", answers={
        "science_value": AnswerDist(kind="choice", choice=sci, confidence=sci_conf, probabilities=dist(levels, sci, sci_conf)),
        "event_type": AnswerDist(kind="choice", choice=etype, confidence=type_conf, probabilities=dist(types, etype, type_conf)),
        "downlink_action": AnswerDist(kind="choice", choice=action, confidence=0.95, probabilities=dist(acts, action, 0.95)),
        "needs_deep_analysis": AnswerDist(kind="noul", noul=deep),
        "instrument_failure": AnswerDist(kind="choice", choice="yes" if fail_yes > 0.5 else "no", confidence=max(fail_yes, 1 - fail_yes),
                                         probabilities={"yes": fail_yes, "no": 1 - fail_yes - 0.0, "uncertain": 0.0}),
    })
