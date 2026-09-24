"""Configuration loading, validation and versioning."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[4]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
PIPELINE_VERSION = "0.1.0"


class Detection(BaseModel):
    rems_window_s: int = 300
    lmst_bin_minutes: int = 30
    baseline_sols: int = 7
    min_samples: int = 30
    z_threshold: float = 4.0
    rad_z_threshold: float = 3.5
    dip_threshold_pa: float = 0.75
    flat_fraction_threshold: float = 0.95
    missing_fraction_threshold: float = 0.5
    noise_ratio_threshold: float = 4.0
    merge_gap_s: int = 900
    coincidence_window_s: int = 3600


class Gating(BaseModel):
    auto_threshold: float = 0.90
    uncertain_threshold: float = 0.70
    deep_request_threshold: float = 0.60


class Thresholds(BaseModel):
    full_data: float = 0.55
    compress: float = 0.42
    summary_only: float = 0.22


class Priority(BaseModel):
    weights: dict[str, float] = Field(
        default_factory=lambda: {"science_value": 0.35, "mission_relevance": 0.30, "anomaly_strength": 0.20, "novelty": 0.15}
    )
    anomaly_scale: float = 6.0
    confidence_penalty: float = 0.5
    cost_exponent: float = 0.5
    thresholds: Thresholds = Field(default_factory=Thresholds)
    engine_action_policy: Literal["ignore", "upgrade_only"] = "upgrade_only"
    instrument_failure_floor: float = 0.6


class Compression(BaseModel):
    decimation_factor: int = 8
    zlib_level: int = 6
    fidelity: dict[str, float] = Field(
        default_factory=lambda: {"full_data": 1.0, "compress": 0.5, "summary_only": 0.15, "discard": 0.0}
    )


class Downlink(BaseModel):
    passes_per_sol: int = 2
    pass_bytes: int = 32768
    storage_bytes: int = 1048576
    background_summary: bool = True
    protect_utility: float | None = None  # None → priority.thresholds.full_data


class Blackout(BaseModel):
    duration_sols: float = 3.0
    storage_bytes: int = 196608


class DecisionEngineCfg(BaseModel):
    kind: Literal["auto", "mock", "jev"] = "auto"  # auto → jev when TYPESAFE_API_KEY is set
    jev_model: str = "jev-latest"
    price_per_mtok_input_usd: float = 0.042
    timeout_s: float = 10
    max_concurrency: int = 8


class DeepCfg(BaseModel):
    provider: Literal["none", "claude"] = "none"
    model: str = "claude-opus-5"


class BenchmarkCfg(BaseModel):
    random_seed: int = 7
    injection_seed: int = 11
    injections_per_sol: float = 1.0


class Config(BaseModel):
    mission: str = "msl_curiosity"
    detection: Detection = Field(default_factory=Detection)
    gating: Gating = Field(default_factory=Gating)
    priority: Priority = Field(default_factory=Priority)
    compression: Compression = Field(default_factory=Compression)
    downlink: Downlink = Field(default_factory=Downlink)
    blackout: Blackout = Field(default_factory=Blackout)
    decision_engine: DecisionEngineCfg = Field(default_factory=DecisionEngineCfg)
    deep_analysis: DeepCfg = Field(default_factory=DeepCfg)
    objective: str = "balanced_science"
    benchmark: BenchmarkCfg = Field(default_factory=BenchmarkCfg)

    def version(self) -> str:
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:12]

    def patched(self, patch: dict[str, Any]) -> "Config":
        """Return a new, validated config with a nested partial update applied."""
        merged = deep_merge(self.model_dump(mode="json"), patch)
        return Config.model_validate(merged)


def deep_merge(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def diff(a: dict, b: dict, prefix: str = "") -> list[dict]:
    changes = []
    for k in sorted(set(a) | set(b)):
        path = f"{prefix}.{k}" if prefix else k
        va, vb = a.get(k), b.get(k)
        if isinstance(va, dict) and isinstance(vb, dict):
            changes.extend(diff(va, vb, path))
        elif va != vb:
            changes.append({"path": path, "before": va, "after": vb})
    return changes


def load_config(path: Path | None = None) -> Config:
    path = path or CONFIG_DIR / "default.yaml"
    return Config.model_validate(yaml.safe_load(path.read_text()) or {})
