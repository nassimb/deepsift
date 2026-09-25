"""The bounded questions every decision engine answers — engine-agnostic.

Wording follows TypeSafe's guidance for Jev: one focused judgment per question, literal
phrasing, and criteria that describe when each option applies. The questions do not mention
the mission objective, so changing the objective never requires new engine calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class QuestionSpec:
    kind: str                      # choice | noul
    instructions: str
    criteria: dict[str, str] = field(default_factory=dict)  # choice: option -> when it applies; noul: true/false


QUESTIONS: dict[str, QuestionSpec] = {
    "science_value": QuestionSpec(
        "choice",
        "How scientifically valuable is this detected Mars surface environmental event for planetary scientists?",
        {
            "none": "Routine conditions or a measurement artefact with no scientific content",
            "low": "Slightly unusual but within normal day-to-day variability",
            "medium": "Clearly unusual and worth a summary, but not rare",
            "high": "A strong, rare or multi-sensor departure from normal conditions that scientists would want to study",
            "critical": "An exceptional event, such as a solar particle event or an extreme atmospheric phenomenon, that must reach Earth",
        },
    ),
    "event_type": QuestionSpec(
        "choice",
        "Which kind of phenomenon best explains this event?",
        {
            "nominal": "Normal variability; nothing physically unusual happened",
            "atmospheric": "A change in the atmosphere: pressure drops or rises, dust, humidity or UV changes",
            "radiation": "A change in the radiation environment measured by the dosimeter",
            "thermal": "A temperature change of the air or ground not explained by the normal daily cycle",
            "instrument_anomaly": "A sensor or data problem: stuck values, dropouts, noise, impossible values or discontinuities",
            "unknown": "None of the above fits clearly",
        },
    ),
    "downlink_action": QuestionSpec(
        "choice",
        "Given limited bandwidth to Earth, what should happen to this event's raw data?",
        {
            "discard": "Delete the raw data; nothing of value would be lost",
            "summary_only": "Send only a short statistical summary",
            "compress": "Send a reduced-resolution version of the raw data",
            "full_data": "Send the complete raw data at full resolution",
        },
    ),
    "needs_deep_analysis": QuestionSpec(
        "noul",
        "This event is ambiguous or important enough that an expert should analyse it in depth before deciding.",
        {"true": "Ambiguous, conflicting or potentially exceptional", "false": "Clear-cut; a quick decision is sufficient"},
    ),
    "instrument_failure": QuestionSpec(
        "choice",
        "Is this event more likely caused by an instrument or data failure than by a natural phenomenon?",
        {
            "yes": "The pattern indicates a sensor or data-handling failure",
            "no": "The pattern is consistent with a real environmental phenomenon",
            "uncertain": "The evidence does not distinguish the two",
        },
    ),
}

# questions whose confidence drives the gating decision
GATING_QUESTIONS = ("science_value", "event_type")


# Ablation: one question only (JEV_SINGLE_DECISION). The strategy uses P(yes) directly as utility.
SINGLE_DECISION_QUESTIONS: dict[str, QuestionSpec] = {
    "retain": QuestionSpec(
        "noul",
        "This detected Mars surface event deserves to have its data retained and sent to Earth with priority.",
        {"true": "Scientifically or operationally valuable enough to spend limited bandwidth on",
         "false": "Routine or uninformative; the bandwidth is better spent elsewhere"},
    ),
}


# ---------------------------------------------------------------------------------------------------
# Question schema versions. "q1" = QUESTIONS above (pre-registered; used by every Phase-2b result so far).
# "q2" = VALIDATION-ONLY wording experiment after pilot 20260925T091126-jev-pilot-7351, which found
# instrument_failure = "yes" on 92–100 % of candidates in every variant (including documented Forbush
# decreases / SEPs and synthetic physical offsets without any quality flag) and "uncertain" never chosen.
# q2 changes ONLY the instrument_failure question and the instrument_anomaly criterion of event_type, to
# separate "specific evidence of a sensor/data problem" from "a large deviation from normal". Answer keys
# are unchanged, so the frozen priority formula reads q2 answers exactly as q1 answers.
# See docs/jev-model-selection.md § Representation changes.
QUESTION_SCHEMA_VERSION = {"q1": "2026-09-25 pre-registered", "q2": "2026-09-25 validation-only wording experiment"}

QUESTIONS_V2: dict[str, QuestionSpec] = dict(QUESTIONS)
QUESTIONS_V2["event_type"] = QuestionSpec(
    "choice",
    QUESTIONS["event_type"].instructions,
    {
        **QUESTIONS["event_type"].criteria,
        "instrument_anomaly": "Specific evidence of a sensor or data problem: stuck or repeated values, missing samples, noise far above "
                              "the sensor's usual level, or physically impossible values. A large deviation from normal, on its own, "
                              "is not evidence of a sensor problem",
    },
)
QUESTIONS_V2["instrument_failure"] = QuestionSpec(
    "choice",
    "Does the evidence specifically suggest malfunction or degradation of the measuring instrument or its data handling, "
    "rather than a natural environmental phenomenon? The size of a deviation from normal conditions, on its own, does not "
    "distinguish the two.",
    {
        "yes": "There is specific evidence of a sensor or data problem: stuck or repeated values, missing samples, noise far above "
               "the sensor's usual level, or physically impossible values",
        "no": "The measurements are physically plausible and show no specific sign of a sensor or data problem",
        "uncertain": "The evidence points both ways, or there is too little information to tell a malfunction from a natural phenomenon",
    },
)
