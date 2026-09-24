"""JevDecisionEngine — TypeSafe AI's Jev via the official `typesafe-sdk` (Python).

All Jev-specific code lives in this file. Verified against typesafe-sdk 0.7.1, whose wire models
are generated from https://api.typesafe.ai/openapi.json:

    client = TypeSafeClient(retry=RetryPolicy(max_retries=0))   # reads TYPESAFE_API_KEY
    resp = client.system_one(state=..., questions={name: Choice(...) | Noul(...)}, model="jev-latest")
    resp.answers[name]  -> ChoiceAnswer(choice, confidence, probabilities) | NoulAnswer(noul)
    resp.usage.input_tokens / output_tokens · resp.model · resp.request_id (x-typesafe-request-id)

SDK retries are disabled; retries happen in this file so the retry count per call is exact.
Every call is appended to a JSONL call log (never the API key).
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from deepsift.core.models import AnswerDist, EngineDecision, ScientificEvent
from deepsift.decision.base import DecisionEngine
from deepsift.decision.questions import QUESTIONS, SINGLE_DECISION_QUESTIONS, QuestionSpec
from deepsift.decision.state import build_state_variant

VARIANTS = {
    # name: (state variant, question set)
    "full_context": ("full_context", "five"),
    "no_mission_objective": ("no_mission_objective", "five"),
    "minimal": ("minimal", "five"),
    "numeric_only": ("numeric_only", "five"),
    "single_decision": ("no_mission_objective", "single"),
}


def jev_available() -> bool:
    return bool(os.environ.get("TYPESAFE_API_KEY", "").strip())


def sdk_version() -> str:
    try:
        from importlib.metadata import version

        return version("typesafe-sdk")
    except Exception:  # noqa: BLE001
        return "unknown"


def build_questions(specs: dict[str, QuestionSpec] | None = None) -> dict:
    from typesafe_sdk import Choice, Noul

    out = {}
    for name, q in (specs or QUESTIONS).items():
        if q.kind == "choice":
            out[name] = Choice(instructions=q.instructions, criteria=dict(q.criteria))
        else:
            out[name] = Noul(instructions=q.instructions, criteria={"true": q.criteria["true"], "false": q.criteria["false"]})
    return out


def questions_payload(specs: dict[str, QuestionSpec]) -> dict:
    return {n: {"type": q.kind, "instructions": q.instructions, "criteria": q.criteria} for n, q in specs.items()}


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


RETRYABLE = ("TypeSafeRateLimitError", "TypeSafeInternalServerError", "TypeSafeAPIConnectionError", "TypeSafeAPITimeoutError")


class JevDecisionEngine(DecisionEngine):
    is_real_model = True

    def __init__(self, model: str = "jev-latest", timeout_s: float = 10.0, max_concurrency: int = 8,
                 price_per_mtok_input_usd: float = 0.042, client=None, variant: str = "no_mission_objective",
                 call_log: Path | None = None, run_id: str | None = None, max_retries: int = 2):
        if variant not in VARIANTS:
            raise ValueError(f"unknown Jev variant {variant}")
        self.model = model
        self.timeout_s = timeout_s
        self.max_concurrency = max_concurrency
        self.price = price_per_mtok_input_usd
        self._client = client
        self.variant = variant
        self.state_variant, qset = VARIANTS[variant]
        self.question_specs = SINGLE_DECISION_QUESTIONS if qset == "single" else QUESTIONS
        self.call_log = call_log
        self.run_id = run_id
        self.max_retries = max_retries
        self._log_lock = threading.Lock()
        self.name = f"jev:{model}:{variant}"

    def describe(self) -> dict:
        return {"name": self.name, "is_real_model": True, "variant": self.variant, "model": self.model,
                "sdk": f"typesafe-sdk {sdk_version()}"}

    def _get_client(self):
        if self._client is None:
            from typesafe_sdk import RetryPolicy, TypeSafeClient

            self._client = TypeSafeClient(timeout=self.timeout_s, retry=RetryPolicy(max_retries=0))
        return self._client

    def _log(self, rec: dict) -> None:
        if self.call_log is None:
            return
        self.call_log.parent.mkdir(parents=True, exist_ok=True)
        with self._log_lock, self.call_log.open("a") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")

    def decide(self, events: list[ScientificEvent], mission_name: str, location: str,
               objective: dict | None = None) -> list[EngineDecision]:
        questions = build_questions(self.question_specs)
        qpayload = questions_payload(self.question_specs)
        client = self._get_client()
        sdkv = sdk_version()

        def one(e: ScientificEvent) -> EngineDecision:
            state = build_state_variant(e, mission_name, location, self.state_variant, objective)
            payload_hash = hashlib.sha256(json.dumps({"state": state, "questions": qpayload, "model": self.model},
                                                     sort_keys=True).encode()).hexdigest()
            attempts, err, resp = 0, None, None
            t0 = time.perf_counter()
            while attempts <= self.max_retries:
                attempts += 1
                try:
                    resp = client.system_one(state=state, questions=questions, model=self.model)
                    err = None
                    break
                except Exception as exc:  # noqa: BLE001 — recorded; gated to deterministic fallback
                    err = f"{type(exc).__name__}: {exc}"[:500]
                    if type(exc).__name__ not in RETRYABLE or attempts > self.max_retries:
                        break
                    time.sleep(min(0.5 * 2 ** (attempts - 1), 5.0))
            latency = (time.perf_counter() - t0) * 1000
            rec = {
                "run_id": self.run_id, "timestamp": datetime.now(timezone.utc).isoformat(), "event_id": e.id,
                "variant": self.variant, "payload_sha256": payload_hash, "state": state, "questions": qpayload,
                "model_requested": self.model, "sdk_version": sdkv, "latency_ms": latency,
                "attempts": attempts, "retries": attempts - 1, "error": err,
            }
            if resp is None:
                self._log(rec)
                return EngineDecision(engine=self.name, model=self.model, error=err, latency_ms=latency, state_sent=state)
            answers = convert_answers(resp)
            tokens_in = getattr(resp.usage, "input_tokens", None)
            try:
                request_id = resp.request_id
            except Exception:  # noqa: BLE001 — header absent
                request_id = None
            rec.update({
                "model_returned": getattr(resp, "model", None), "request_id": request_id,
                "answers": {k: v.model_dump() for k, v in answers.items()},
                "input_tokens": tokens_in, "output_tokens": getattr(resp.usage, "output_tokens", None),
            })
            self._log(rec)
            return EngineDecision(
                engine=self.name, model=getattr(resp, "model", self.model), answers=answers, latency_ms=latency,
                input_tokens=tokens_in, output_tokens=getattr(resp.usage, "output_tokens", None),
                cost_usd=(tokens_in * self.price / 1e6) if tokens_in is not None else None, state_sent=state,
            )

        with ThreadPoolExecutor(max_workers=self.max_concurrency) as pool:
            return list(pool.map(one, events))


def missing_key_instructions() -> str:
    return (
        "TYPESAFE_API_KEY is not set, so every Jev strategy is reported UNAVAILABLE.\n"
        "To enable it (do not paste the key into chat):\n"
        "  1. cp .env.example .env            (in the DEEPSIFT repository root)\n"
        "  2. edit .env and set  TYPESAFE_API_KEY=<your key>\n"
        "  3. export it for CLI runs:  set -a; . ./.env; set +a\n"
        "  4. uv run python scripts/jev_smoke.py      (verifies one call before any benchmark)\n"
        "`npm run demo` and scripts/run_study.py load .env automatically."
    )
