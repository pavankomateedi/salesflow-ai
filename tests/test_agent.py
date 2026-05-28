from __future__ import annotations

from salesflow.agent.agent import Playbook, SalesAgent
from salesflow.config import SETTINGS
from salesflow.domain.models import ConversationState, Lead, Phase
from salesflow.knowledge.kb import ObjectionType


def _fresh() -> tuple[SalesAgent, ConversationState]:
    return SalesAgent(), ConversationState(lead=Lead(phone="+15550001111"))


def test_open_plays_recording_disclosure() -> None:
    agent, state = _fresh()
    action = agent.open(state)
    assert "recorded" in action.utterance.lower()
    assert action.phase == Phase.WARMUP


def test_pricing_answer_is_grounded_in_config() -> None:
    agent, state = _fresh()
    agent.open(state)
    action = agent.respond(state, "Sure. By the way, how much does it cost?")
    # Every quoted figure must come from the structured pricing config.
    for rate in SETTINGS.pricing.plans.values():
        assert f"${rate}" in action.utterance
    assert "pricing-config" in action.grounded_sources


def test_unanswerable_policy_question_escalates_low_confidence() -> None:
    agent, state = _fresh()
    agent.open(state)
    action = agent.respond(state, "What is your tutor's exact state license number?")
    assert action.phase == Phase.ESCALATION
    assert action.escalation is not None
    assert action.escalation.value == "low_confidence"


def test_explicit_human_request_escalates_immediately() -> None:
    agent, state = _fresh()
    agent.open(state)
    action = agent.respond(state, "Just let me talk to a real person.")
    assert action.escalation is not None
    assert action.escalation.value == "explicit_request"


def test_objection_uses_arc_rebuttal_and_clears() -> None:
    agent, state = _fresh()
    agent.open(state)
    action = agent.respond(state, "Honestly this sounds too expensive.")
    assert action.objection == ObjectionType.PRICE
    assert action.phase == Phase.OBJECTION_HANDLING
    assert "objections" in action.grounded_sources
    # A-R-C closes by clearing the objection so it no longer blocks the pivot.
    assert "price" not in state.open_objections
    assert "price" in state.resolved_objections


def test_ab_playbook_override_swaps_rebuttal_text() -> None:
    variant = Playbook(
        name="roi-framing",
        objection_overrides={ObjectionType.PRICE: "Think of it as an investment in their GPA."},
    )
    agent = SalesAgent(playbook=variant)
    state = ConversationState(lead=Lead(phone="+15550002222"))
    agent.open(state)
    action = agent.respond(state, "That's too expensive for us.")
    assert "investment in their GPA" in action.utterance
    assert "variant" in action.grounded_sources


def test_known_fields_are_not_re_asked() -> None:
    agent = SalesAgent()
    lead = Lead(phone="+15550003333", known={"student_name": "Mia", "grade_level": "8th"})
    state = ConversationState(lead=lead)
    agent.open(state)
    action = agent.respond(state, "Yes, good time to talk.")
    # First two required fields are known -> agent jumps to 'subjects'.
    assert action.asked_field == "subjects"
