"""Mission objective layer — structured, versionable, and applied without re-running the pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from deepsift.core.config import CONFIG_DIR, DATA_DIR
from deepsift.core.models import EventType

CUSTOM_PATH = DATA_DIR / "processed" / "objectives_custom.json"


class MissionObjective(BaseModel):
    id: str
    name: str
    description: str = ""
    type_weights: dict[str, float]
    channel_weights: dict[str, float] = Field(default_factory=dict)
    priority_weights: dict[str, float] | None = None
    custom: bool = False

    @field_validator("type_weights")
    @classmethod
    def _complete(cls, v: dict[str, float]) -> dict[str, float]:
        out = {t.value: float(v.get(t.value, 0.0)) for t in EventType}
        for k, x in out.items():
            if not 0.0 <= x <= 1.0:
                raise ValueError(f"type weight {k}={x} outside [0, 1]")
        return out

    @field_validator("channel_weights")
    @classmethod
    def _bounded(cls, v: dict[str, float]) -> dict[str, float]:
        for k, x in v.items():
            if not 0.0 <= x <= 1.0:
                raise ValueError(f"channel weight {k}={x} outside [0, 1]")
        return v

    def relevance(self, type_probs: dict[str, float], flagged_channels: list[str]) -> tuple[float, str]:
        """Return (relevance in [0, 1], which rule produced it)."""
        by_type = sum(p * self.type_weights.get(t, 0.0) for t, p in type_probs.items())
        by_channel = max((self.channel_weights.get(c, 0.0) for c in flagged_channels), default=0.0)
        if by_channel > by_type:
            ch = max(flagged_channels, key=lambda c: self.channel_weights.get(c, 0.0))
            return by_channel, f"channel weight {ch}={by_channel:.2f}"
        return by_type, "Σ P(type)·type_weight"


def load_objectives(path: Path | None = None) -> dict[str, MissionObjective]:
    raw = yaml.safe_load((path or CONFIG_DIR / "objectives.yaml").read_text())
    out = {k: MissionObjective(id=k, **v) for k, v in raw.items()}
    if CUSTOM_PATH.exists():
        for k, v in json.loads(CUSTOM_PATH.read_text()).items():
            out[k] = MissionObjective(**v)
    return out


def save_custom(obj: MissionObjective) -> None:
    CUSTOM_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(CUSTOM_PATH.read_text()) if CUSTOM_PATH.exists() else {}
    existing[obj.id] = obj.model_dump(mode="json") | {"custom": True}
    CUSTOM_PATH.write_text(json.dumps(existing, indent=2))
