"""Run the decisioning core against the golden set — the executable spec.

Every case here is exact-match. A failure means the agent's behaviour diverged
from the agreed spec, not that "it looked off".
"""

from __future__ import annotations

import pytest

import salesflow.personas as personas
from salesflow.agent.escalation import classify_escalation
from salesflow.agent.pivot import pivot_ready
from salesflow.agent.question_selector import next_field
from salesflow.analysis import is_close_affirmation
from salesflow.config import SETTINGS
from salesflow.domain.models import REQUIRED_FIELDS, ConversationState, Lead, Outcome, Phase
from salesflow.domain.phases import can_transition
from salesflow.eval.golden import load_golden_set
from salesflow.eval.harness import run_call
from salesflow.knowledge.kb import KnowledgeBase, ObjectionType, classify_objection

GOLDEN = load_golden_set()


@pytest.mark.parametrize("case", GOLDEN["objection_classification"])
def test_objection_classification(case: dict) -> None:
    result = classify_objection(case["input"])
    expected = ObjectionType(case["expected"]) if case["expected"] else None
    assert result == expected, case["input"]


@pytest.mark.parametrize("case", GOLDEN["question_selection"])
def test_question_selection(case: dict) -> None:
    lead = Lead(phone="+15550000000", known=dict(case["known"]))
    assert next_field(lead) == case["expected"]


@pytest.mark.parametrize("case", GOLDEN["rag_retrieval"])
def test_rag_retrieval(case: dict) -> None:
    kb = KnowledgeBase()
    chunks = kb.retrieve(case["query"], k=1)
    assert chunks, f"no retrieval for {case['query']!r}"
    assert chunks[0].source == case["expected_source"]
    assert case["title_contains"].lower() in chunks[0].title.lower()


@pytest.mark.parametrize("case", GOLDEN["phase_transitions"])
def test_phase_transitions(case: dict) -> None:
    assert can_transition(Phase(case["from"]), Phase(case["to"])) is case["allowed"]


@pytest.mark.parametrize("case", GOLDEN["escalation"])
def test_escalation(case: dict) -> None:
    state = ConversationState(lead=Lead(phone="+15550000000"))
    for key, value in case.get("state", {}).items():
        setattr(state, key, value)
    decision = classify_escalation(
        state,
        case["text"],
        settings=SETTINGS,
        policy_question_unanswerable=case.get("policy_unanswerable", False),
    )
    actual = decision.trigger.value if decision else None
    assert actual == case["expected"], case["text"]


@pytest.mark.parametrize("case", GOLDEN["pivot"])
def test_pivot(case: dict) -> None:
    if case["all_required"]:
        known = {f: "known" for f in REQUIRED_FIELDS}
    else:
        known = {"student_name": "Sam"}
    known.update(case["leading"])
    state = ConversationState(lead=Lead(phone="+15550000000", known=known))
    state.positive_signals = case["positive_signals"]
    state.open_objections = list(case["open_objections"])
    state.disqualify_signals = case["disqualify_signals"]
    assert pivot_ready(state, SETTINGS).ready is case["expected_ready"], case["description"]


@pytest.mark.parametrize("case", GOLDEN["close_affirmation"])
def test_close_affirmation(case: dict) -> None:
    """Tight close detection: bare 'Yes.' closes, polite let-downs don't.

    Encodes the regression that broke the A/B simulation when a broad
    positive-sentiment check falsely closed calls on 'I'll think about it,
    thanks.' Each row is exact-match against ``is_close_affirmation``.
    """
    assert is_close_affirmation(case["text"]) is case["expected"], case["text"]


@pytest.mark.parametrize("case", GOLDEN["self_play"])
def test_self_play_outcomes(case: dict) -> None:
    from salesflow.agent.agent import SalesAgent

    persona_cls = getattr(personas, case["persona"])
    agent = SalesAgent()
    lead = Lead(phone="+15550000001")
    log = run_call(agent, persona_cls(), lead, session_id=case["persona"])
    assert log.outcome == Outcome(case["expected_outcome"]), case["persona"]
    expected_esc = case["expected_escalation"]
    actual_esc = log.escalation_trigger.value if log.escalation_trigger else None
    assert actual_esc == expected_esc, case["persona"]
