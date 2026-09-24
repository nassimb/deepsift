"""DecisionEngine abstraction. Engines *judge*; they never act."""

from __future__ import annotations

from abc import ABC, abstractmethod

from deepsift.core.models import EngineDecision, ScientificEvent


class DecisionEngine(ABC):
    name: str = "abstract"
    is_real_model: bool = False   # False for heuristic stand-ins — surfaced in every UI/benchmark label

    @abstractmethod
    def decide(self, events: list[ScientificEvent], mission_name: str, location: str) -> list[EngineDecision]:
        """Return one decision per event, in order. Must not raise for a single bad event."""

    def describe(self) -> dict:
        return {"name": self.name, "is_real_model": self.is_real_model}
