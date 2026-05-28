"""Self-play simulation harness.

Drives a :class:`SalesAgent` against a scripted :class:`Persona` to completion
and returns a :class:`CallLog`. Deterministic and offline — this is the spec the
golden set and KPI scorers run against.
"""

from __future__ import annotations

from salesflow.agent.agent import SalesAgent
from salesflow.domain.models import CallLog, ConversationState, Lead
from salesflow.personas import ALL_PERSONAS, Persona

MAX_TURNS = 60


def run_call(
    agent: SalesAgent,
    persona: Persona,
    lead: Lead,
    *,
    session_id: str,
    max_turns: int = MAX_TURNS,
) -> CallLog:
    """Run one full self-play call and return its log."""
    state = ConversationState(lead=lead)
    action = agent.open(state)
    turns = 0
    while not state.phase.is_terminal and turns < max_turns:
        reply = persona.reply(action, state)
        action = agent.respond(state, reply)
        turns += 1
    return _to_call_log(state, session_id=session_id, version=agent.version)


def run_suite(
    agent_factory: type[SalesAgent] | None = None,
    *,
    agent: SalesAgent | None = None,
    personas: list[type[Persona]] | None = None,
) -> list[CallLog]:
    """Run a fresh agent (or the provided one) against every persona.

    A fresh agent per call keeps state isolated; pass ``agent`` to reuse a
    specific configuration (e.g. an A/B variant playbook).
    """
    persona_types = personas or ALL_PERSONAS
    logs: list[CallLog] = []
    for i, ptype in enumerate(persona_types):
        call_agent = agent or SalesAgent()
        persona = ptype()
        lead = Lead(phone=f"+1555000{i:04d}")
        logs.append(
            run_call(call_agent, persona, lead, session_id=f"{persona.name}-{i}".replace(" ", "_"))
        )
    return logs


def _to_call_log(state: ConversationState, *, session_id: str, version: str) -> CallLog:
    decisions = [t.decision for t in state.turns if t.speaker == "agent" and t.decision]
    return CallLog(
        session_id=session_id,
        phone=state.lead.phone,
        agent_version=version,
        turns=list(state.turns),
        outcome=state.outcome,
        final_phase=state.phase,
        escalation_trigger=state.escalation_trigger,
        collected_fields=dict(state.lead.all_fields),
        decisions=decisions,
    )
