"""Core data models for a SalesFlow conversation.

Everything here is plain ``dataclasses`` + ``Enum`` so call state is trivially
serialisable into transcripts and decision logs (the observability layer) and
trivially asserted against in the golden set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Phase(StrEnum):
    """The 7 functional sales phases plus the terminal ESCALATION state.

    Ordered roughly by progression; ``GRACEFUL_EXIT`` and ``ESCALATION`` are
    terminal off-ramps reachable from most phases.
    """

    WARMUP = "warmup"
    DISCOVERY = "discovery"
    QUALIFICATION = "qualification"
    OBJECTION_HANDLING = "objection_handling"
    PIVOT_TO_CLOSE = "pivot_to_close"
    CLOSE = "close"
    GRACEFUL_EXIT = "graceful_exit"
    ESCALATION = "escalation"

    @property
    def is_terminal(self) -> bool:
        return self in (Phase.CLOSE, Phase.GRACEFUL_EXIT, Phase.ESCALATION)


class EscalationTrigger(StrEnum):
    """The 5 escalation trigger types from the PRD."""

    LOW_CONFIDENCE = "low_confidence"
    HIGH_STAKES_PRICING = "high_stakes_pricing"
    NEGATIVE_SENTIMENT = "negative_sentiment"
    EXPLICIT_REQUEST = "explicit_request"
    DISQUALIFICATION_UNCERTAINTY = "disqualification_uncertainty"


class Outcome(StrEnum):
    """Terminal call outcome, used for KPI attribution."""

    IN_PROGRESS = "in_progress"
    CLOSED_WON = "closed_won"
    GRACEFUL_EXIT = "graceful_exit"
    ESCALATED = "escalated"
    DISQUALIFIED = "disqualified"


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"

    @property
    def score(self) -> float:
        """Numeric anger/negativity score in [0, 1] (1 == most negative)."""
        return {"positive": 0.0, "neutral": 0.3, "negative": 0.9}[self.value]


# ---------------------------------------------------------------------------
# Field definitions (the question script)
# ---------------------------------------------------------------------------

# Required fields are always collected unless already known from a prior call.
REQUIRED_FIELDS: tuple[str, ...] = (
    "student_name",
    "grade_level",
    "subjects",
    "performance_level",
    "parent_contact",
    "urgency",
)

# Leading fields, ordered by predictive conversion value (highest first).
LEADING_FIELDS: tuple[str, ...] = (
    "prior_tutoring",
    "test_deadline",
    "schedule_windows",
    "decision_maker",
    "budget_signal",
)


# ---------------------------------------------------------------------------
# Lead
# ---------------------------------------------------------------------------


@dataclass
class Lead:
    """A prospect record. May arrive with full data, partial data, or none.

    ``known`` holds whatever fields are already populated coming into the call
    (e.g. from a prior session keyed by session-id + phone). ``collected`` holds
    fields gathered during the current call. ``all_fields`` merges them.
    """

    phone: str
    known: dict[str, str] = field(default_factory=dict)
    collected: dict[str, str] = field(default_factory=dict)

    @property
    def all_fields(self) -> dict[str, str]:
        merged = dict(self.known)
        merged.update(self.collected)
        return merged

    def is_known(self, field_name: str) -> bool:
        """True if the field is already populated (prior data or collected)."""
        value = self.all_fields.get(field_name)
        return value is not None and value.strip() != ""

    def missing_required(self) -> list[str]:
        return [f for f in REQUIRED_FIELDS if not self.is_known(f)]

    def missing_leading(self) -> list[str]:
        return [f for f in LEADING_FIELDS if not self.is_known(f)]

    def discovery_complete(self) -> bool:
        return not self.missing_required()


# ---------------------------------------------------------------------------
# Turn + conversation state
# ---------------------------------------------------------------------------


@dataclass
class Turn:
    """One utterance in the conversation, with the decision context behind it."""

    speaker: str  # "agent" | "prospect"
    text: str
    phase: Phase
    sentiment: Sentiment = Sentiment.NEUTRAL
    confidence: float = 1.0
    # Free-form decision trace for the observability layer (why this turn happened).
    decision: dict[str, object] = field(default_factory=dict)


@dataclass
class ConversationState:
    """Mutable state threaded through the decisioning engine for one call."""

    lead: Lead
    phase: Phase = Phase.WARMUP
    turns: list[Turn] = field(default_factory=list)
    open_objections: list[str] = field(default_factory=list)
    resolved_objections: list[str] = field(default_factory=list)
    positive_signals: int = 0
    disqualify_signals: int = 0
    probe_attempts: int = 0
    negative_streak: int = 0
    outcome: Outcome = Outcome.IN_PROGRESS
    escalation_trigger: EscalationTrigger | None = None
    asked_fields: list[str] = field(default_factory=list)

    def add_turn(self, turn: Turn) -> None:
        self.turns.append(turn)

    @property
    def agent_turns(self) -> list[Turn]:
        return [t for t in self.turns if t.speaker == "agent"]

    @property
    def prospect_turns(self) -> list[Turn]:
        return [t for t in self.turns if t.speaker == "prospect"]


@dataclass
class CallLog:
    """Immutable record of a completed call for the observability layer."""

    session_id: str
    phone: str
    agent_version: str
    turns: list[Turn]
    outcome: Outcome
    final_phase: Phase
    escalation_trigger: EscalationTrigger | None
    collected_fields: dict[str, str]
    decisions: list[dict[str, object]] = field(default_factory=list)
