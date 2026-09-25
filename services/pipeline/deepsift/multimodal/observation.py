"""M10 — MultimodalObservation: one image ACQUISITION plus its telemetry context, location and downlink options.

No fusion score yet (candidate_score / priority stay None until the checkpoint is approved).
Evaluation categories are separate fields and are never combined into one number.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DownlinkOptions(BaseModel):
    full_bytes: float | None                 # onboard-compressed primaries (all eyes), from label COMPRESSION_PARMS
    compressed_bytes: float | None           # DEEPSIFT ground re-encoding (JPEG q50 of the primary) — measured, not onboard
    thumbnail_bytes: float | None            # the rover's own thumbnail product, from its label
    metadata_bytes: int                      # compact JSON metadata record, measured
    archive_bytes: int                       # PDS archive bytes of all products (decompressed 16-bit) — NOT a downlink cost
    full_bytes_status: str                   # "ESTIMATED_FROM_LABEL" | "UNKNOWN"


class MultimodalObservation(BaseModel):
    id: str
    mission: str = "MSL"
    instrument: str = "NAVCAM"
    sol: int
    utc: str
    sclk: float
    sequence_id: str
    stereo: bool
    primary_tier: str
    image_products: list[str]
    image_features: dict[str, Any]                   # quality metrics, phash, embedding novelty
    quality_state: str                               # CLEAN / SUSPECT / BAD — engineering only
    telemetry_context: dict[str, Any]
    location_context: dict[str, Any]
    near_duplicate_group: int
    sequence_group: int
    scene_cluster: int                               # evaluation reference (metadata only)
    downlink: DownlinkOptions
    candidate_score: float | None = None             # reserved for fusion (not implemented before the checkpoint)
    priority: float | None = None
    annotations: dict[str, Any] = Field(default_factory=lambda: {
        "documented_science_event": None, "human_annotation": None, "synthetic_visual_anomaly": None})
    source_metadata: dict[str, Any] = Field(default_factory=dict)
