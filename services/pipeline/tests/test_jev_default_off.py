"""Jev is not in the default ranking path after phase2-complete (pre-registered stop rule); it stays opt-in."""

from pathlib import Path

from deepsift.core.config import ROOT, load_config
from deepsift.decision.jev import JevDecisionEngine
from deepsift.decision.mock import MockDecisionEngine
from deepsift.evaluation.study import Study
from deepsift.pipeline import make_engine


def test_auto_config_does_not_select_jev_even_with_a_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.delenv("DEEPSIFT_EXPERIMENTAL_JEV", raising=False)
    for cfg_path in (ROOT / "config" / "phase2.yaml", ROOT / "config" / "default.yaml"):
        assert isinstance(make_engine(load_config(Path(cfg_path))), MockDecisionEngine)


def test_jev_still_available_behind_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("DEEPSIFT_EXPERIMENTAL_JEV", "1")
    assert isinstance(make_engine(load_config(ROOT / "config" / "phase2.yaml")), JevDecisionEngine)


def test_study_defaults_to_no_jev():
    import inspect

    assert inspect.signature(Study.__init__).parameters["use_jev"].default is False
