"""JevDecisionEngine — TypeSafe AI's Jev via the official `typesafe-sdk` (Python), routed through OpenRouter.

All Jev-specific code lives in this file. Verified against typesafe-sdk 0.7.1 and OpenRouter's System One
API (https://openrouter.ai/docs/guides/community/typesafe-sdk, retrieved 2026-09-25): the SDK is pointed
at OpenRouter by base URL; nothing else in the SDK call changes.

    client = TypeSafeClient(api_key=$OPENROUTER_API_KEY, base_url="https://openrouter.ai/api",
                            retry=RetryPolicy(max_retries=0))      # POST /api/v1/systemone
    resp = client.system_one(state=..., questions={name: Choice(...) | Noul(...)}, model="typesafe/jev-1.13")
    resp.answers[name]  -> ChoiceAnswer(choice, confidence, probabilities) | NoulAnswer(noul)
    resp.usage.input_tokens / output_tokens · resp.model (served snapshot)
    OpenRouter extras the SDK ignores, read from resp.raw_http_response: id, provider, usage.cost (USD)

TYPESAFE_API_KEY / TYPESAFE_BASE_URL are never read: key and base URL are passed explicitly.

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
from deepsift.decision.questions import QUESTIONS, QUESTIONS_V2, SINGLE_DECISION_QUESTIONS, QuestionSpec
from deepsift.decision.state import build_state_variant

VARIANTS = {
    # name: (state variant, question set)
    "full_context": ("full_context", "five"),
    "no_mission_objective": ("no_mission_objective", "five"),
    "minimal": ("minimal", "five"),
    "numeric_only": ("numeric_only", "five"),
    "single_decision": ("no_mission_objective", "single"),
}
# Validation-only question-schema experiments. Kept OUT of VARIANTS so the pre-registered five are unchanged.
SCHEMA_VARIANTS = {
    "no_mission_objective@q2": ("no_mission_objective", "five_q2"),
}
ALL_VARIANTS = {**VARIANTS, **SCHEMA_VARIANTS}
QUESTION_SETS = {"five": QUESTIONS, "five_q2": QUESTIONS_V2, "single": SINGLE_DECISION_QUESTIONS}


def question_specs_for(variant: str) -> dict[str, QuestionSpec]:
    return QUESTION_SETS[ALL_VARIANTS[variant][1]]


TRANSPORT = "openrouter"
BASE_URL = "https://openrouter.ai/api"
ENDPOINT = BASE_URL + "/v1/systemone"
KEY_ENV = "OPENROUTER_API_KEY"


def jev_available() -> bool:
    return bool(os.environ.get(KEY_ENV, "").strip())


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


class JevBudgetExceeded(RuntimeError):
    """Raised before an API call that would exceed the run's hard call budget."""


class ApiBudget:
    """Thread-safe hard limit on live API calls for one run (cache hits are free)."""

    def __init__(self, max_calls: int, max_cost_usd: float):
        self.max_calls = max_calls
        self.max_cost_usd = max_cost_usd
        self.calls = 0
        self.cost_usd = 0.0
        self._lock = threading.Lock()

    def reserve(self) -> None:
        with self._lock:
            if self.calls >= self.max_calls:
                raise JevBudgetExceeded(f"hard limit reached: {self.calls} live Jev calls (JEV_MAX_CALLS={self.max_calls})")
            if self.cost_usd >= self.max_cost_usd:
                raise JevBudgetExceeded(f"hard limit reached: ${self.cost_usd:.4f} (JEV_MAX_COST_USD={self.max_cost_usd})")
            self.calls += 1

    def add_cost(self, usd: float | None) -> None:
        with self._lock:
            self.cost_usd += usd or 0.0


FATAL = ("TypeSafeAuthenticationError", "TypeSafePermissionDeniedError")   # stop sending after the first one


RETRYABLE = ("TypeSafeRateLimitError", "TypeSafeInternalServerError", "TypeSafeAPIConnectionError", "TypeSafeAPITimeoutError")


class JevDecisionEngine(DecisionEngine):
    is_real_model = True

    def __init__(self, model: str = "typesafe/jev-1.13", timeout_s: float = 10.0, max_concurrency: int = 8,
                 price_per_mtok_input_usd: float = 0.042, client=None, variant: str = "no_mission_objective",
                 call_log: Path | None = None, run_id: str | None = None, max_retries: int = 2,
                 cache=None, use_cache: bool = True, budget: ApiBudget | None = None):
        if variant not in ALL_VARIANTS:
            raise ValueError(f"unknown Jev variant {variant}")
        self.model = model
        self.timeout_s = timeout_s
        self.max_concurrency = max_concurrency
        self.price = price_per_mtok_input_usd
        self._client = client
        self.variant = variant
        self.state_variant = ALL_VARIANTS[variant][0]
        self.question_specs = question_specs_for(variant)
        self.call_log = call_log
        self.run_id = run_id
        self.max_retries = max_retries
        self._log_lock = threading.Lock()
        self.name = f"jev:{model}:{variant}"
        if use_cache and cache is None:
            from deepsift.decision.jev_cache import JevCache

            cache = JevCache()
        self.cache = cache if use_cache else None
        self.budget = budget
        self.stats = {"cache_hits": 0, "live_calls": 0, "errors": 0}
        self.fatal_error: str | None = None

    def describe(self) -> dict:
        return {"name": self.name, "is_real_model": True, "variant": self.variant, "model": self.model,
                "transport": TRANSPORT, "endpoint": ENDPOINT, "sdk": f"typesafe-sdk {sdk_version()}"}

    def _get_client(self):
        if self._client is None:
            from typesafe_sdk import RetryPolicy, TypeSafeClient

            self._client = TypeSafeClient(api_key=os.environ[KEY_ENV].strip(), base_url=BASE_URL,
                                          timeout=self.timeout_s, retry=RetryPolicy(max_retries=0))
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
            from deepsift.decision.jev_cache import request_key

            payload_hash = request_key(state, qpayload, self.variant, self.model, sdkv, TRANSPORT)
            if self.cache is not None:
                hit = self.cache.get(payload_hash)
                if hit is not None:
                    self.stats["cache_hits"] += 1
                    answers = {k: AnswerDist(**v) for k, v in hit["answers"].items()}
                    self._log({"run_id": self.run_id, "timestamp": datetime.now(timezone.utc).isoformat(), "event_id": e.id,
                               "variant": self.variant, "payload_sha256": payload_hash, "cache_hit": True,
                               "cached_from_run": hit["run_id"], "model_returned": hit["model_returned"], "transport": TRANSPORT})
                    return EngineDecision(engine=self.name, model=hit["model_returned"], answers=answers,
                                          latency_ms=hit["latency_ms"] or 0.0, input_tokens=hit["input_tokens"],
                                          output_tokens=hit["output_tokens"], cost_usd=0.0, state_sent=state)
            if self.fatal_error:                            # fail fast: never repeat a rejected credential
                return EngineDecision(engine=self.name, model=self.model, error=f"not sent: {self.fatal_error}", state_sent=state)
            if self.budget is not None:
                self.budget.reserve()                       # raises before any call beyond the hard limit
            self.stats["live_calls"] += 1
            attempts, err, resp, http_status, err_body = 0, None, None, None, None
            t0 = time.perf_counter()
            while attempts <= self.max_retries:
                attempts += 1
                try:
                    resp = client.system_one(state=state, questions=questions, model=self.model)
                    err = None
                    break
                except Exception as exc:  # noqa: BLE001 — recorded; gated to deterministic fallback
                    err = f"{type(exc).__name__}: {exc}"[:500]
                    http_status, err_body = getattr(exc, "status", None), getattr(exc, "body", None)
                    if type(exc).__name__ in FATAL:
                        self.fatal_error = err
                        break
                    if type(exc).__name__ not in RETRYABLE or attempts > self.max_retries:
                        break
                    time.sleep(min(0.5 * 2 ** (attempts - 1), 5.0))
            latency = (time.perf_counter() - t0) * 1000
            rec = {
                "run_id": self.run_id, "timestamp": datetime.now(timezone.utc).isoformat(), "event_id": e.id,
                "variant": self.variant, "payload_sha256": payload_hash, "state": state, "questions": qpayload,
                "model_requested": self.model, "sdk_version": sdkv, "transport": TRANSPORT, "endpoint": ENDPOINT,
                "latency_ms": latency, "attempts": attempts, "retries": attempts - 1, "error": err,
                "http_status": http_status, "error_body": err_body,
            }
            rec["cache_hit"] = False
            if resp is None:
                self.stats["errors"] += 1
                self._log(rec)
                return EngineDecision(engine=self.name, model=self.model, error=err, latency_ms=latency, state_sent=state)
            answers = convert_answers(resp)
            tokens_in = getattr(resp.usage, "input_tokens", None)
            extra = openrouter_extras(resp)
            request_id = extra["generation_id"]
            if request_id is None:
                try:
                    request_id = resp.request_id
                except Exception:  # noqa: BLE001 — header absent
                    pass
            derived = (tokens_in * self.price / 1e6) if tokens_in is not None else None
            cost = extra["cost_usd"] if extra["cost_usd"] is not None else derived
            rec.update({
                "http_status": extra["http_status"], "model_returned": getattr(resp, "model", None), "provider": extra["provider"],
                "request_id": request_id, "answers": {k: v.model_dump() for k, v in answers.items()},
                "input_tokens": tokens_in, "output_tokens": getattr(resp.usage, "output_tokens", None),
                "cost_usd": cost, "cost_source": "usage.cost" if extra["cost_usd"] is not None else "derived",
                "cost_usd_derived": derived,
            })
            self._log(rec)
            if self.budget is not None:
                self.budget.add_cost(cost)
            if self.cache is not None:
                self.cache.put(payload_hash, event_id=e.id, variant=self.variant, model_requested=self.model,
                               model_returned=getattr(resp, "model", None), sdk_version=sdkv, request_id=request_id,
                               questions=qpayload, state=state, answers={k: v.model_dump() for k, v in answers.items()},
                               latency_ms=latency, input_tokens=tokens_in, output_tokens=getattr(resp.usage, "output_tokens", None),
                               cost_usd=cost, run_id=self.run_id)
            return EngineDecision(
                engine=self.name, model=getattr(resp, "model", self.model), answers=answers, latency_ms=latency,
                input_tokens=tokens_in, output_tokens=getattr(resp.usage, "output_tokens", None),
                cost_usd=cost, state_sent=state,
            )

        with ThreadPoolExecutor(max_workers=self.max_concurrency) as pool:
            return list(pool.map(one, events))


def openrouter_extras(resp) -> dict:
    """OpenRouter fields the SDK's strict models drop (id, provider, usage.cost), read from the raw body."""
    out = {"http_status": None, "generation_id": None, "provider": None, "cost_usd": None}
    try:
        raw = resp.raw_http_response
        out["http_status"] = raw.status_code
        body = raw.json()
    except Exception:  # noqa: BLE001 — injected test clients have no raw response
        return out
    usage = body.get("usage") or {}
    out.update(generation_id=body.get("id"), provider=body.get("provider"),
               cost_usd=float(usage["cost"]) if isinstance(usage.get("cost"), (int, float)) else None)
    return out


def missing_key_instructions() -> str:
    return (
        f"{KEY_ENV} is not set, so every Jev strategy is reported UNAVAILABLE.\n"
        "Jev is called through OpenRouter's System One API (TYPESAFE_API_KEY is not used).\n"
        "To enable it (do not paste the key into chat):\n"
        "  1. cp .env.example .env            (in the DEEPSIFT repository root)\n"
        f"  2. edit .env and set  {KEY_ENV}=<your OpenRouter key>\n"
        "  3. export it for CLI runs:  set -a; . ./.env; set +a\n"
        "  4. uv run python scripts/jev_smoke.py      (verifies one call before any benchmark)\n"
        "`npm run demo` and scripts/run_study.py load .env automatically."
    )
