"""Structured configuration.

Pricing and thresholds live here, never in an LLM prompt (PRD: "Pricing injected
from structured config layer, not LLM"). This module is the single source of
truth the grounding judge checks agent claims against.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Pricing:
    """Authoritative pricing. The agent may only quote numbers from here."""

    plans: dict[str, int] = field(
        default_factory=lambda: {
            "starter": 40,  # USD / hour, month-to-month
            "standard": 60,  # USD / hour, includes progress reports
            "intensive": 90,  # USD / hour, test-prep + dedicated tutor
        }
    )
    # Largest discount the agent may offer autonomously, as a fraction.
    max_autonomous_discount: float = 0.10

    def hourly(self, plan: str) -> int | None:
        return self.plans.get(plan)


@dataclass(frozen=True)
class Thresholds:
    """Decisioning thresholds for the escalation classifier and pivot logic."""

    # Escalation
    min_llm_confidence: float = 0.6
    negative_sentiment_streak: int = 2  # consecutive turns above anger threshold
    max_probe_attempts: int = 3  # before disqualification-uncertainty escalation
    # Pivot-to-close requires this many positive engagement signals.
    pivot_positive_signals: int = 1


@dataclass(frozen=True)
class Settings:
    pricing: Pricing = field(default_factory=Pricing)
    thresholds: Thresholds = field(default_factory=Thresholds)
    # Recording disclosure auto-played at connection (TCPA).
    recording_disclosure: str = (
        "Hi, this is Vani from Nerdy. This call may be recorded for quality. "
    )


SETTINGS = Settings()
