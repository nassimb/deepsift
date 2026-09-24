"""MissionAdapter — the only mission-specific surface of DEEPSIFT.

An adapter turns a mission's archival products into two mission-agnostic tables:

  samples  (long format, one row per channel measurement)
      t: Datetime[UTC]  sol: Int32  lmst_s: Float64  instrument: Utf8  channel: Utf8
      value: Float64  record: Int64  product: Utf8

  records  (one row per original archival record — the unit of byte accounting)
      instrument: Utf8  product: Utf8  record: Int64  t: Datetime[UTC]  bytes: Int64

plus a per-window byte table computed from the *actual* record bytes (see `window_bytes`).
Everything downstream (features, detection, decisions, simulation, evaluation) only sees these
tables, so a Perseverance MEDA, lunar or Earth-observation adapter plugs in without pipeline edits.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import polars as pl

from deepsift.core.models import DataSource


@dataclass(frozen=True)
class ChannelSpec:
    name: str
    instrument: str
    unit: str
    min_sigma: float          # noise floor for robust z (avoids divide-by-~0 MAD)
    physical_range: tuple[float, float]
    diurnal: bool = True      # baseline by local-time bin (True) or whole-sol (False)
    description: str = ""


@dataclass
class MissionMetadata:
    id: str
    name: str
    short_name: str
    target: str
    instruments: dict[str, str]
    channels: list[ChannelSpec]
    sol_length_s: float
    location: str
    data_citations: list[str]
    data_source: DataSource = DataSource.NASA_PDS
    sols: list[int] = field(default_factory=list)
    products: list[str] = field(default_factory=list)


@dataclass
class LoadedMission:
    samples: pl.DataFrame
    records: pl.DataFrame
    window_bytes: pl.DataFrame   # instrument, window_key, raw, full, compressed, row_start, row_end, products
    metadata: MissionMetadata


class MissionAdapter(ABC):
    """Interface every mission implements."""

    @abstractmethod
    def metadata(self) -> MissionMetadata: ...

    @abstractmethod
    def load(self, sols: list[int] | None = None) -> None:
        """Locate and read raw products (download cache or bundled fixture)."""

    @abstractmethod
    def normalize(self) -> LoadedMission:
        """Return mission-agnostic samples/records/window byte tables."""

    @abstractmethod
    def window_key(self, instrument: str) -> pl.Expr:
        """Expression mapping a samples/records row to its analysis window for `instrument`."""

    def extract_events(self, config, injections=None):
        """Run the generic, mission-agnostic feature + detection stages on this mission."""
        from deepsift.features.detect import detect_events

        mission = self.normalize()
        return detect_events(mission, self, config, injections=injections)
