"""KPI scorers — turn a batch of call logs into the PRD's tracked metrics.

All metrics are computed deterministically from the decision logs so the same
numbers drive both the dashboard and the A/B promotion decision.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from salesflow.domain.models import REQUIRED_FIELDS, CallLog, Outcome, Phase


@dataclass
class KPIReport:
    n_calls: int
    conversion_rate: float
    discovery_completion_rate: float
    escalation_rate: float
    objection_to_close_rate: float
    false_positive_close_rate: float
    avg_handle_turns: float
    transcript_quality: float
    outcomes: dict[str, int]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _engaged(call: CallLog) -> bool:
    """A call is 'engaged' once the agent has begun asking discovery fields."""
    return call.final_phase != Phase.WARMUP and any(
        d.get("step") == "ask_field" for d in call.decisions
    )


def _discovery_complete(call: CallLog) -> bool:
    return all(call.collected_fields.get(f) for f in REQUIRED_FIELDS)


def _had_objection(call: CallLog) -> bool:
    return any(d.get("step") == "objection" for d in call.decisions)


def _false_positive_close(call: CallLog) -> bool:
    """A close where the 5 pivot signals were not all satisfied."""
    if call.outcome != Outcome.CLOSED_WON:
        return False
    for d in call.decisions:
        if d.get("step") == "close":
            pivot = d.get("pivot") or {}
            if isinstance(pivot, dict) and not all(pivot.values()):
                return True
    return False


def _transcript_quality(call: CallLog) -> float:
    """Deterministic proxy in [0, 5]; the LLM judge augments grounding scoring.

    Rewards reaching a clean terminal state; penalises stalling out (hitting the
    turn cap with no outcome).
    """
    if call.outcome == Outcome.IN_PROGRESS:
        return 2.5  # stalled / hit the turn cap
    return 5.0


def score_calls(calls: list[CallLog]) -> KPIReport:
    n = len(calls)
    if n == 0:
        return KPIReport(0, 0, 0, 0, 0, 0, 0, 0, {})

    closed = [c for c in calls if c.outcome == Outcome.CLOSED_WON]
    escalated = [c for c in calls if c.outcome == Outcome.ESCALATED]
    engaged = [c for c in calls if _engaged(c)]
    with_objection = [c for c in calls if _had_objection(c)]
    obj_closed = [c for c in with_objection if c.outcome == Outcome.CLOSED_WON]
    fp_closes = [c for c in closed if _false_positive_close(c)]

    outcomes: dict[str, int] = {}
    for c in calls:
        outcomes[c.outcome.value] = outcomes.get(c.outcome.value, 0) + 1

    return KPIReport(
        n_calls=n,
        conversion_rate=len(closed) / n,
        discovery_completion_rate=(
            sum(_discovery_complete(c) for c in engaged) / len(engaged) if engaged else 0.0
        ),
        escalation_rate=len(escalated) / n,
        objection_to_close_rate=(len(obj_closed) / len(with_objection) if with_objection else 0.0),
        false_positive_close_rate=(len(fp_closes) / len(closed) if closed else 0.0),
        avg_handle_turns=sum(len(c.turns) for c in calls) / n,
        transcript_quality=sum(_transcript_quality(c) for c in calls) / n,
        outcomes=outcomes,
    )
