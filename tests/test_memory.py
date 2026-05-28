from __future__ import annotations

from salesflow.agent.agent import SalesAgent
from salesflow.memory import SessionStore


def test_double_key_prevents_cross_session_contamination() -> None:
    store = SessionStore()
    store.remember("sess-A", {"student_name": "Mia"}, phone="+15551234567")
    # Same phone, different session -> recycled number must NOT inherit data.
    assert store.known_fields("sess-B", "+15551234567") == {}
    assert store.known_fields("sess-A", "+15551234567") == {"student_name": "Mia"}


def test_known_fields_carry_over_and_are_not_re_asked() -> None:
    store = SessionStore()
    store.remember(
        "sess-1", {"student_name": "Mia", "grade_level": "8th"}, phone="+15550009999"
    )
    lead = store.load_lead("sess-1", "+15550009999")
    agent = SalesAgent()
    from salesflow.domain.models import ConversationState

    state = ConversationState(lead=lead)
    agent.open(state)
    action = agent.respond(state, "Yes, good time.")
    # Prior name + grade are known, so the agent skips straight to 'subjects'.
    assert action.asked_field == "subjects"


def test_persistence_round_trip(tmp_path) -> None:
    path = tmp_path / "sessions.json"
    SessionStore(path).remember("s", {"urgency": "soon"}, phone="+1555")
    assert SessionStore(path).known_fields("s", "+1555") == {"urgency": "soon"}
