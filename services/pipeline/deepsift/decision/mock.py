"""MockDecisionEngine — a transparent, deterministic heuristic stand-in for a decision model.

It exists so DEEPSIFT runs end-to-end without an API key. It is NOT a model, it was written by
the same people who wrote the synthetic anomaly generator, and any benchmark row produced with it
says so. Probabilities come from a softmax over hand-set logits of the event features; the
reported confidence is the top-option probability.
"""

from __future__ import annotations

import math
import time

from deepsift.core.models import AnswerDist, EngineDecision, ScientificEvent
from deepsift.decision.base import DecisionEngine
from deepsift.decision.state import build_state
from deepsift.features.detect import QUALITY_FLAGS

ATMOS = {"pressure", "uv_abc", "rel_humidity"}
THERMAL = {"air_temp", "ground_temp"}


def softmax(logits: dict[str, float], temperature: float = 1.0) -> dict[str, float]:
    m = max(logits.values())
    ex = {k: math.exp((v - m) / temperature) for k, v in logits.items()}
    s = sum(ex.values())
    return {k: round(v / s, 4) for k, v in ex.items()}


def _choice(probs: dict[str, float]) -> AnswerDist:
    top = max(probs, key=probs.get)
    return AnswerDist(kind="choice", choice=top, confidence=probs[top], probabilities=probs)


class MockDecisionEngine(DecisionEngine):
    name = "mock-heuristic-v1"
    is_real_model = False

    def decide(self, events: list[ScientificEvent], mission_name: str, location: str,
               objective: dict | None = None) -> list[EngineDecision]:
        return [self._one(e, mission_name, location) for e in events]

    def _one(self, e: ScientificEvent, mission_name: str, location: str) -> EngineDecision:
        t0 = time.perf_counter()
        f = e.features
        ch = f.channels
        flagged = set(e.sensors)
        dev = f.deviation_score
        quality = sum(
            1 for k, c in ch.items() if k in flagged and set(c.flags) & QUALITY_FLAGS
        )
        # implausible level jumps: RAD dose collapsing to <30 % of baseline is not a known natural process
        implausible = any(
            c.baseline and c.baseline > 0 and c.mean is not None and c.mean < 0.3 * c.baseline for c in ch.values() if e.instrument == "RAD"
        )
        dip_flag = "pressure" in ch and "dip" in ch["pressure"].flags

        inst = 1.2 * quality + (3.0 if implausible else 0.0)
        type_logits = {
            "nominal": 1.5 - 0.35 * dev,
            "atmospheric": 0.9 * len(flagged & ATMOS) + (1.5 if dip_flag else 0.0) - 0.5 * quality,
            "radiation": (2.5 + 0.1 * min(dev, 20)) if e.instrument == "RAD" and not implausible else -2.0,
            "thermal": 0.9 * len(flagged & THERMAL) - 0.4 * quality,
            "instrument_anomaly": inst,
            "unknown": 0.4 + (0.6 if f.correlated_channels >= 3 else 0.0),
        }
        type_p = softmax(type_logits, temperature=0.45)

        strength = 1 - math.exp(-dev / 6)
        sci = (
            2.2 * strength + 1.2 * max(f.rarity_score - 0.8, 0) * 5 / 5 + 0.35 * min(f.correlated_channels, 4)
            + (0.6 if f.cross_instrument_coincidence else 0.0) + 0.5 * f.novelty
            + (0.8 if f.duration_s > 3 * 3600 and e.instrument == "RAD" else 0.0)
            - 1.4 * type_p["instrument_anomaly"] - 1.0 * type_p["nominal"]
        )
        levels = {"none": 0.0, "low": 1.0, "medium": 2.0, "high": 3.0, "critical": 4.0}
        centre = max(0.0, min(4.0, sci * 1.25))
        sci_p = softmax({k: -((v - centre) ** 2) / 0.3 for k, v in levels.items()})

        expected = sum(levels[k] * p for k, p in sci_p.items())
        act_levels = {"discard": 0.0, "summary_only": 1.3, "compress": 2.3, "full_data": 3.2}
        act_p = softmax({k: -((v - expected) ** 2) / 0.3 for k, v in act_levels.items()})

        fail_p = softmax({
            "yes": inst - 0.5,
            "no": 0.8 + 0.3 * len(flagged & ATMOS) + (1.2 if e.instrument == "RAD" and not implausible else 0) - inst,
            "uncertain": 0.3,
        })
        entropy = -sum(p * math.log(p + 1e-12) for p in type_p.values()) / math.log(len(type_p))
        deep = min(1.0, 0.55 * entropy + 0.35 * sci_p["critical"] + 0.3 * sci_p["high"])

        answers = {
            "science_value": _choice(sci_p),
            "event_type": _choice(type_p),
            "downlink_action": _choice(act_p),
            "needs_deep_analysis": AnswerDist(kind="noul", noul=round(deep, 4)),
            "instrument_failure": _choice(fail_p),
        }
        return EngineDecision(
            engine=self.name, model=None, answers=answers,
            latency_ms=(time.perf_counter() - t0) * 1000,
            state_sent=build_state(e, mission_name, location),
        )
