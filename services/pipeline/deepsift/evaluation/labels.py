"""Evaluation labels. Sources are kept distinct and are never merged with model predictions."""

from __future__ import annotations

from datetime import datetime

import yaml
from pydantic import BaseModel

from deepsift.core.config import DATA_DIR
from deepsift.core.models import LabelSource

SEVERITY_WEIGHT = {"low": 1.0, "medium": 2.0, "high": 3.0}


class Label(BaseModel):
    id: str
    source: LabelSource
    instrument: str | None
    t_start: datetime
    t_end: datetime
    expected_type: str | None = None
    severity: str = "medium"
    description: str = ""
    reference: str | None = None
    status: str | None = None


def documented_labels() -> list[Label]:
    path = DATA_DIR / "labels" / "documented_events.yaml"
    if not path.exists():
        return []
    return [Label(source=LabelSource.DOCUMENTED_EVENT, **{k: v for k, v in d.items()})
            for d in yaml.safe_load(path.read_text()) or []]


def synthetic_labels(injections) -> list[Label]:
    out = []
    for inj in injections:
        instrument = "RAD" if set(inj.channels) <= {"dose_b", "dose_e"} else "REMS"
        out.append(Label(
            id=inj.id, source=LabelSource.SYNTHETIC_ANOMALY, instrument=instrument, t_start=inj.t_start, t_end=inj.t_end,
            expected_type=inj.expected_type, severity=inj.severity,
            description=f"injected {inj.kind} on {', '.join(inj.channels)} (magnitude {inj.magnitude})",
        ))
    return out


def human_labels(rows: list[dict]) -> list[Label]:
    out = []
    for r in rows:
        if r.get("source") != LabelSource.HUMAN_LABEL.value:
            continue
        out.append(Label(id=r["label_id"], source=LabelSource.HUMAN_LABEL, instrument=r.get("instrument"),
                         t_start=datetime.fromisoformat(r["t_start"].replace("Z", "+00:00")),
                         t_end=datetime.fromisoformat(r["t_end"].replace("Z", "+00:00")),
                         expected_type=r.get("expected_type"), severity=r.get("severity", "medium"),
                         description=r.get("note", "")))
    return out
