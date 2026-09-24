"""DeepAnalysisProvider — expensive, rarely-invoked second opinion.

Only events that the gating layer escalates reach a provider. The provider receives the compact
event state, the mission context and objective, and short same-channel history — never raw
datasets. Its verdict is bounded (JSON schema); its free-text rationale is stored and always
displayed as model-generated text.
"""

from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod

from deepsift.core.models import DeepAnalysis, EventType, InstrumentFailure, ScienceValue

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "science_value": {"type": "string", "enum": [v.value for v in ScienceValue]},
        "event_type": {"type": "string", "enum": [v.value for v in EventType]},
        "instrument_failure": {"type": "string", "enum": [v.value for v in InstrumentFailure]},
        "rationale": {"type": "string"},
    },
    "required": ["science_value", "event_type", "instrument_failure", "rationale"],
    "additionalProperties": False,
}


class DeepAnalysisProvider(ABC):
    name = "abstract"
    available = False

    @abstractmethod
    def analyze(self, state: dict, mission_context: dict, objective: dict, history: list[dict]) -> DeepAnalysis: ...


class NoDeepAnalysis(DeepAnalysisProvider):
    """Explicit 'unavailable' provider: escalations fall back to deterministic rules."""

    name = "none"
    available = False

    def analyze(self, state, mission_context, objective, history) -> DeepAnalysis:
        return DeepAnalysis(provider=self.name, error="deep analysis unavailable (no provider configured)")


class ClaudeDeepAnalysis(DeepAnalysisProvider):
    """Anthropic Claude via the official `anthropic` SDK with structured JSON output."""

    name = "claude"

    def __init__(self, model: str = "claude-opus-5"):
        self.model = model
        self.available = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
        self._client = None

    def analyze(self, state, mission_context, objective, history) -> DeepAnalysis:
        t0 = time.perf_counter()
        try:
            import anthropic

            if self._client is None:
                self._client = anthropic.Anthropic()
            prompt = (
                "You are reviewing one candidate event detected by an onboard science-triage system on a Mars rover.\n"
                "Judge it only from the evidence below. Do not invent measurements or cite events not shown.\n\n"
                f"MISSION CONTEXT\n{json.dumps(mission_context, indent=1)}\n\n"
                f"ACTIVE MISSION OBJECTIVE\n{json.dumps(objective, indent=1)}\n\n"
                f"EVENT (aggregated features; raw rows not included)\n{json.dumps(state, indent=1)}\n\n"
                f"RECENT HISTORY OF THE SAME CHANNELS (window means vs baseline)\n{json.dumps(history[:40], indent=1)}\n\n"
                "Return your verdict. Keep the rationale under 80 words and cite only the evidence above."
            )
            response = self._client.beta.messages.create(
                model=self.model,
                max_tokens=2048,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={"format": {"type": "json_schema", "schema": VERDICT_SCHEMA}},
                messages=[{"role": "user", "content": prompt}],
            )
            latency = (time.perf_counter() - t0) * 1000
            if response.stop_reason == "refusal":
                return DeepAnalysis(provider=self.name, model=self.model, latency_ms=latency, error="model refused")
            text = next(b.text for b in response.content if b.type == "text")
            v = json.loads(text)
            return DeepAnalysis(
                provider=self.name, model=response.model, science_value=ScienceValue(v["science_value"]),
                event_type=EventType(v["event_type"]), instrument_failure=InstrumentFailure(v["instrument_failure"]),
                rationale=v["rationale"], latency_ms=latency,
            )
        except Exception as exc:  # noqa: BLE001 — recorded; pipeline falls back to rules
            return DeepAnalysis(provider=self.name, model=self.model, latency_ms=(time.perf_counter() - t0) * 1000,
                                error=f"{type(exc).__name__}: {exc}"[:500])


def make_provider(kind: str, model: str) -> DeepAnalysisProvider:
    if kind == "claude":
        p = ClaudeDeepAnalysis(model)
        return p if p.available else NoDeepAnalysis()
    return NoDeepAnalysis()
