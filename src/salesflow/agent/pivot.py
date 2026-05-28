"""Pivot-to-close trigger — the 5-signal threshold.

All five must hold before the agent pivots to asking for commitment. Keeping it
explicit (not an LLM vibe-check) is what makes the false-positive-close rate
measurable and the decision auditable.
"""

from __future__ import annotations

from dataclasses import dataclass

from salesflow.config import Settings
from salesflow.domain.models import ConversationState


@dataclass(frozen=True)
class PivotSignals:
    required_complete: bool
    qualification_confirmed: bool
    no_open_objections: bool
    has_positive_signal: bool
    no_disqualifier: bool

    @property
    def ready(self) -> bool:
        return all(
            (
                self.required_complete,
                self.qualification_confirmed,
                self.no_open_objections,
                self.has_positive_signal,
                self.no_disqualifier,
            )
        )

    def as_dict(self) -> dict[str, bool]:
        return {
            "required_complete": self.required_complete,
            "qualification_confirmed": self.qualification_confirmed,
            "no_open_objections": self.no_open_objections,
            "has_positive_signal": self.has_positive_signal,
            "no_disqualifier": self.no_disqualifier,
        }


def pivot_ready(state: ConversationState, settings: Settings) -> PivotSignals:
    """Compute the 5 pivot signals from current conversation state."""
    lead = state.lead
    # Qualification: at minimum we need timeline (urgency) plus one of the
    # budget/authority leading fields to confirm fit.
    qualification_confirmed = lead.is_known("urgency") and (
        lead.is_known("budget_signal") or lead.is_known("decision_maker")
    )
    return PivotSignals(
        required_complete=lead.discovery_complete(),
        qualification_confirmed=qualification_confirmed,
        no_open_objections=not state.open_objections,
        has_positive_signal=state.positive_signals >= settings.thresholds.pivot_positive_signals,
        no_disqualifier=state.disqualify_signals == 0,
    )
