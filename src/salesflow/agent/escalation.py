"""The escalation classifier — the 5 trigger types from the PRD.

Thresholds are intentionally conservative (PRD decision: "Conservative initial
escalation thresholds"); it is easier to reduce escalation rate later than to
recover from a bad autonomous answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from salesflow import analysis
from salesflow.config import Settings
from salesflow.domain.models import ConversationState, EscalationTrigger

_DISCOUNT_PCT_RE = re.compile(r"(\d{1,3})\s*%")
_DISCOUNT_CUES = ("discount", "deal", "lower", "knock off", "cheaper", "match", "price")


@dataclass(frozen=True)
class EscalationDecision:
    trigger: EscalationTrigger
    reason: str


def _requested_discount_fraction(text: str) -> float | None:
    """Extract a requested discount as a fraction, if the prospect named one."""
    low = text.lower()
    if not any(cue in low for cue in _DISCOUNT_CUES):
        return None
    m = _DISCOUNT_PCT_RE.search(low)
    if m:
        return int(m.group(1)) / 100.0
    return None


def classify_escalation(
    state: ConversationState,
    prospect_text: str,
    *,
    settings: Settings,
    policy_question_unanswerable: bool = False,
) -> EscalationDecision | None:
    """Return an escalation decision if any trigger fires, else None.

    Evaluated in priority order: an explicit request for a human always wins,
    since the PRD requires immediate, frictionless escalation.
    """
    th = settings.thresholds

    # 1. Explicit request — immediate, no friction.
    if analysis.requests_human(prospect_text):
        return EscalationDecision(
            EscalationTrigger.EXPLICIT_REQUEST,
            "Prospect explicitly asked to speak with a person.",
        )

    # 2. Extreme negative sentiment sustained across consecutive turns.
    if state.negative_streak >= th.negative_sentiment_streak:
        return EscalationDecision(
            EscalationTrigger.NEGATIVE_SENTIMENT,
            f"Negative sentiment for {state.negative_streak} consecutive turns.",
        )

    # 3. High-stakes pricing: concession above the autonomous limit.
    frac = _requested_discount_fraction(prospect_text)
    if frac is not None and frac > settings.pricing.max_autonomous_discount:
        return EscalationDecision(
            EscalationTrigger.HIGH_STAKES_PRICING,
            f"Requested discount {frac:.0%} exceeds autonomous limit "
            f"{settings.pricing.max_autonomous_discount:.0%}.",
        )

    # 4. Low confidence on a policy/pricing question we cannot ground.
    if policy_question_unanswerable:
        return EscalationDecision(
            EscalationTrigger.LOW_CONFIDENCE,
            "Policy/pricing question could not be grounded in the knowledge base.",
        )

    # 5. Disqualification uncertainty after repeated probing.
    if state.probe_attempts > th.max_probe_attempts:
        return EscalationDecision(
            EscalationTrigger.DISQUALIFICATION_UNCERTAINTY,
            f"Could not determine fit after {state.probe_attempts} probes.",
        )

    return None
