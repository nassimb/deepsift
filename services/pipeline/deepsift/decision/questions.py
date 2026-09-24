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
