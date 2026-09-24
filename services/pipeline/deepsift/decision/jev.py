"""JevDecisionEngine — TypeSafe AI's Jev via the official `typesafe-sdk` (Python).

All Jev-specific code lives in this file. Verified against typesafe-sdk 0.7.1, whose wire models
are generated from https://api.typesafe.ai/openapi.json:

    client = TypeSafeClient()                      # reads TYPESAFE_API_KEY
    resp = client.system_one(state=..., questions={name: Choice(...) | Noul(...)}, model="jev-latest")
    resp.answers[name]  -> ChoiceAnswer(choice, confidence, probabilities)
                         | NoulAnswer(noul)          # P(yes); no separate confidence field
    resp.usage.input_tokens / output_tokens
    resp.model                                      # resolved model name (alias may differ)

Nothing else from the SDK is assumed.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor

from deepsift.core.models import AnswerDist, EngineDecision, ScientificEvent
from deepsift.decision.base import DecisionEngine
from deepsift.decision.questions import QUESTIONS
from deepsift.decision.state import build_state


def jev_available() -> bool:
    return bool(os.environ.get("TYPESAFE_API_KEY", "").strip())


def build_questions() -> dict:
    from typesafe_sdk import Choice, Noul

    out = {}
    for name, q in QUESTIONS.items():
        if q.kind == "choice":
            out[name] = Choice(instructions=q.instructions, criteria=dict(q.criteria))
        else:
            out[name] = Noul(instructions=q.instructions, criteria={"true": q.criteria["true"], "false": q.criteria["false"]})
    return out


def convert_answers(resp) -> dict[str, AnswerDist]:
    """Map SDK answer objects to DEEPSIFT AnswerDist without re-interpreting them."""
    out: dict[str, AnswerDist] = {}
    for name, a in resp.answers.items():
        kind = getattr(a, "type", None)
        if kind == "choice":
            out[name] = AnswerDist(kind="choice", choice=a.choice, confidence=a.confidence,
                                   probabilities={str(k): float(v) for k, v in a.probabilities.items()})
        elif kind == "noul":
            out[name] = AnswerDist(kind="noul", noul=float(a.noul))
        elif kind == "score":
            out[name] = AnswerDist(kind="score", score=float(a.score), confidence=a.confidence,
                                   probabilities={str(k): float(v) for k, v in a.probabilities.items()})
    return out


class JevDecisionEngine(DecisionEngine):
    is_real_model = True

    def __init__(self, model: str = "jev-latest", timeout_s: float = 10.0, max_concurrency: int = 8,
                 price_per_mtok_input_usd: float = 0.042, client=None):
        self.model = model
        self.timeout_s = timeout_s
        self.max_concurrency = max_concurrency
        self.price = price_per_mtok_input_usd
        self._client = client
        self.name = f"jev:{model}"

    def _get_client(self):
        if self._client is None:
            from typesafe_sdk import TypeSafeClient

            self._client = TypeSafeClient(timeout=self.timeout_s)
        return self._client

    def decide(self, events: list[ScientificEvent], mission_name: str, location: str) -> list[EngineDecision]:
        questions = build_questions()
        client = self._get_client()

        def one(e: ScientificEvent) -> EngineDecision:
            state = build_state(e, mission_name, location)
            t0 = time.perf_counter()
            try:
                resp = client.system_one(state=state, questions=questions, model=self.model)
            except Exception as exc:  # noqa: BLE001 — recorded, gated to deterministic fallback
                return EngineDecision(engine=self.name, model=self.model, error=f"{type(exc).__name__}: {exc}"[:500],
                                      latency_ms=(time.perf_counter() - t0) * 1000, state_sent=state)
            latency = (time.perf_counter() - t0) * 1000
            tokens_in = getattr(resp.usage, "input_tokens", None)
            return EngineDecision(
                engine=self.name, model=getattr(resp, "model", self.model), answers=convert_answers(resp),
                latency_ms=latency, input_tokens=tokens_in, output_tokens=getattr(resp.usage, "output_tokens", None),
                cost_usd=(tokens_in * self.price / 1e6) if tokens_in is not None else None, state_sent=state,
            )

        with ThreadPoolExecutor(max_workers=self.max_concurrency) as pool:
            return list(pool.map(one, events))
