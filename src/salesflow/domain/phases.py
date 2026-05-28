"""The auditable 7-phase sales state machine.

Transitions are an explicit allow-list rather than free-form LLM control, so
every phase change is auditable and per-phase KPI attribution is possible
(PRD decision: "Phase state machine over pure LLM free-form conversation").
"""

from __future__ import annotations

from salesflow.domain.models import Phase

# Allowed forward/lateral transitions. ESCALATION and GRACEFUL_EXIT are
# reachable from any non-terminal phase, handled in ``can_transition``.
ALLOWED_TRANSITIONS: dict[Phase, set[Phase]] = {
    Phase.WARMUP: {Phase.DISCOVERY},
    Phase.DISCOVERY: {Phase.QUALIFICATION, Phase.OBJECTION_HANDLING},
    Phase.QUALIFICATION: {Phase.OBJECTION_HANDLING, Phase.PIVOT_TO_CLOSE},
    # Objection handling returns to qualification or advances once resolved.
    Phase.OBJECTION_HANDLING: {Phase.QUALIFICATION, Phase.PIVOT_TO_CLOSE},
    Phase.PIVOT_TO_CLOSE: {Phase.CLOSE, Phase.OBJECTION_HANDLING},
    Phase.CLOSE: set(),
    Phase.GRACEFUL_EXIT: set(),
    Phase.ESCALATION: set(),
}

# Off-ramps available from any non-terminal phase.
_OFF_RAMPS: set[Phase] = {Phase.ESCALATION, Phase.GRACEFUL_EXIT}


def can_transition(src: Phase, dst: Phase) -> bool:
    """Return True iff moving from ``src`` to ``dst`` is permitted."""
    if src.is_terminal:
        return False
    if dst in _OFF_RAMPS:
        return True
    return dst in ALLOWED_TRANSITIONS.get(src, set())


class IllegalTransitionError(RuntimeError):
    """Raised when an unauthorised phase transition is attempted."""


class PhaseMachine:
    """Guards phase transitions and records the path taken (for auditing)."""

    def __init__(self, start: Phase = Phase.WARMUP) -> None:
        self.current = start
        self.history: list[Phase] = [start]

    def transition(self, dst: Phase) -> Phase:
        if not can_transition(self.current, dst):
            raise IllegalTransitionError(
                f"Illegal transition {self.current.value} -> {dst.value}"
            )
        self.current = dst
        self.history.append(dst)
        return self.current
