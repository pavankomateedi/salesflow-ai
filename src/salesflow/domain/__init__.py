"""Domain models and the auditable 7-phase sales state machine."""

from salesflow.domain.models import (
    LEADING_FIELDS,
    REQUIRED_FIELDS,
    CallLog,
    ConversationState,
    EscalationTrigger,
    Lead,
    Outcome,
    Phase,
    Sentiment,
    Turn,
)
from salesflow.domain.phases import ALLOWED_TRANSITIONS, PhaseMachine, can_transition

__all__ = [
    "ALLOWED_TRANSITIONS",
    "LEADING_FIELDS",
    "REQUIRED_FIELDS",
    "CallLog",
    "ConversationState",
    "EscalationTrigger",
    "Lead",
    "Outcome",
    "Phase",
    "PhaseMachine",
    "Sentiment",
    "Turn",
    "can_transition",
]
