"""Typed domain model shared by every DEEPSIFT layer.

Design rule: provenance concepts are separate types and are never merged.
  * DataSource        — where the bytes came from (real PDS download, bundled NASA sample, synthetic)
  * LabelSource       — where an evaluation label came from (documented, human, synthetic injection, rule)
  * EngineDecision    — what a decision engine *predicted*. A prediction is never a label.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DataSource(StrEnum):
    NASA_PDS = "NASA_PDS"                    # downloaded from the Planetary Data System this session
    LOCAL_NASA_SAMPLE = "LOCAL_NASA_SAMPLE"  # real PDS bytes bundled in data/fixtures
    SYNTHETIC_TEST_DATA = "SYNTHETIC_TEST_DATA"


class LabelSource(StrEnum):
    DOCUMENTED_EVENT = "DOCUMENTED_EVENT"
    HUMAN_LABEL = "HUMAN_LABEL"
    SYNTHETIC_ANOMALY = "SYNTHETIC_ANOMALY"
    RULE_GENERATED = "RULE_GENERATED"


class ScienceValue(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


SCIENCE_VALUE_NUMERIC = {
    ScienceValue.NONE: 0.0,
    ScienceValue.LOW: 0.25,
    ScienceValue.MEDIUM: 0.5,
    ScienceValue.HIGH: 0.75,
    ScienceValue.CRITICAL: 1.0,
}


class EventType(StrEnum):
    NOMINAL = "nominal"
    ATMOSPHERIC = "atmospheric"
    RADIATION = "radiation"
    THERMAL = "thermal"
    INSTRUMENT_ANOMALY = "instrument_anomaly"
    UNKNOWN = "unknown"


class DownlinkAction(StrEnum):
    DISCARD = "discard"
    SUMMARY_ONLY = "summary_only"
    COMPRESS = "compress"
    FULL_DATA = "full_data"


ACTION_RANK = {
    DownlinkAction.DISCARD: 0,
    DownlinkAction.SUMMARY_ONLY: 1,
    DownlinkAction.COMPRESS: 2,
    DownlinkAction.FULL_DATA: 3,
}
RANK_ACTION = {v: k for k, v in ACTION_RANK.items()}


class InstrumentFailure(StrEnum):
    YES = "yes"
    NO = "no"
    UNCERTAIN = "uncertain"


class GateStatus(StrEnum):
    AUTO = "auto"                  # confidence >= auto threshold
    UNCERTAIN = "uncertain"        # kept, flagged for review
    FALLBACK = "fallback"          # low confidence → deterministic rules decided
    ESCALATED = "escalated"        # low confidence / engine request → deep analysis ran
    ENGINE_ERROR = "engine_error"  # engine failed → deterministic rules decided


class ChannelFeatures(BaseModel):
    """Statistical features of one sensor channel within one event."""

    channel: str
    unit: str
    n: int
    mean: float | None                 # None when the channel has no samples in the event (dropout)
    std: float
    min: float | None
    max: float | None
    baseline: float | None = None      # median at the nearest local time over prior sols
    baseline_mad: float | None = None
    robust_z: float = 0.0              # (value − baseline) / (1.4826·MAD), signed extreme over the event
    dip: float = 0.0                   # largest drop below a 60 s running median (pressure vortices)
    rate_of_change: float = 0.0        # least-squares slope, unit/s
    flat_fraction: float = 0.0         # fraction of consecutive identical samples (stuck sensor)
    missing_fraction: float = 0.0      # fraction of expected samples absent (dropout)
    noise_ratio: float = 0.0           # std(first differences) / baseline std(first differences)
    rarity: float = 0.0                # empirical tail probability rank of |robust_z| in history (0..1)
    flags: list[str] = Field(default_factory=list)  # detector flags raised on this channel: level|dip|stuck|dropout|noise|range


class EventFeatures(BaseModel):
    deviation_score: float             # max |robust_z| across channels
    rarity_score: float                # max channel rarity
    duration_s: float
    rate_of_change: float              # max |slope| normalised by channel baseline MAD
    correlated_channels: int           # channels individually over threshold
    cross_instrument_coincidence: bool # overlapping candidate on another instrument (±window)
    novelty: float = 1.0               # 1 − max similarity to earlier events (0..1)
    most_similar_event: str | None = None
    lmst_hour: float
    trigger_reasons: list[str] = Field(default_factory=list)
    channels: dict[str, ChannelFeatures]


class SourceReference(BaseModel):
    instrument: str
    products: list[str]                # PDS product file names
    row_start: int | None = None       # first record index inside the product (REMS)
    row_end: int | None = None
    data_source: DataSource


class ByteCosts(BaseModel):
    """All numbers are measured on the event's actual records, not assumed."""

    raw: int                           # bytes of the original PDS records
    full: int                          # zlib-compressed original records (lossless)
    compressed: int                    # zlib of 1-in-N decimated records (lossy)
    summary: int                       # size of the JSON feature summary


class AnswerDist(BaseModel):
    """One bounded answer from a decision engine, as returned (never re-interpreted)."""

    kind: str                          # choice | score | noul
    choice: str | None = None
    score: float | None = None
    noul: float | None = None
    confidence: float | None = None
    probabilities: dict[str, float] = Field(default_factory=dict)


class EngineDecision(BaseModel):
    engine: str                        # e.g. "mock-heuristic-v1", "jev:jev-1.13"
    model: str | None = None
    answers: dict[str, AnswerDist] = Field(default_factory=dict)
    latency_ms: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    error: str | None = None
    state_sent: dict[str, Any] | None = None  # exactly what the engine saw


class DeepAnalysis(BaseModel):
    provider: str
    model: str | None = None
    science_value: ScienceValue | None = None
    event_type: EventType | None = None
    instrument_failure: InstrumentFailure | None = None
    rationale: str | None = None       # model-generated text; always displayed as such
    latency_ms: float = 0.0
    error: str | None = None


class PriorityBreakdown(BaseModel):
    science_value: float               # expected value from the engine distribution (0..1)
    mission_relevance: float           # Σ p(type)·objective weight (0..1)
    anomaly_strength: float            # deterministic, from deviation_score (0..1)
    novelty: float                     # 1 − similarity (0..1)
    confidence: float                  # min confidence of the gating questions
    weights: dict[str, float]
    contributions: dict[str, float]    # weight × term
    utility: float                     # Σ contributions × confidence penalty
    confidence_penalty: float
    density: float                     # utility per KB^β, used by the scheduler


class ScientificEvent(BaseModel):
    id: str
    mission: str
    instrument: str
    sol: int
    timestamp_start: str               # ISO-8601 UTC
    timestamp_end: str
    sol_start: float                   # sol + LMST fraction, for mission timeline
    sol_end: float
    sensors: list[str]
    features: EventFeatures
    source: SourceReference
    bytes: ByteCosts
    synthetic_injection_ids: list[str] = Field(default_factory=list)

    # decision plane (filled later)
    decision: EngineDecision | None = None
    deep: DeepAnalysis | None = None
    gate: GateStatus | None = None
    priority: PriorityBreakdown | None = None
    proposed_action: DownlinkAction | None = None   # priority engine output
    final_action: DownlinkAction | None = None      # after storage/downlink constraints
    downlink_bytes: int = 0
    status: str = "detected"
    explanation: list[str] = Field(default_factory=list)
    gate_reason: str | None = None
    trace: list[dict[str, Any]] = Field(default_factory=list)   # per-stage timings (measured or amortized)
