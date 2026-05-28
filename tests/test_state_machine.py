from __future__ import annotations

import pytest

from salesflow.domain.models import Phase
from salesflow.domain.phases import IllegalTransitionError, PhaseMachine, can_transition


def test_terminal_phases_have_no_exits() -> None:
    for terminal in (Phase.CLOSE, Phase.GRACEFUL_EXIT, Phase.ESCALATION):
        assert terminal.is_terminal
        assert not can_transition(terminal, Phase.DISCOVERY)


def test_offramps_reachable_from_any_active_phase() -> None:
    for src in (Phase.WARMUP, Phase.DISCOVERY, Phase.QUALIFICATION, Phase.PIVOT_TO_CLOSE):
        assert can_transition(src, Phase.ESCALATION)
        assert can_transition(src, Phase.GRACEFUL_EXIT)


def test_machine_records_history_and_guards() -> None:
    m = PhaseMachine()
    m.transition(Phase.DISCOVERY)
    m.transition(Phase.QUALIFICATION)
    assert m.history == [Phase.WARMUP, Phase.DISCOVERY, Phase.QUALIFICATION]
    with pytest.raises(IllegalTransitionError):
        m.transition(Phase.WARMUP)  # backwards is illegal
