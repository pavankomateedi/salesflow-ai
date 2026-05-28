"""Adversarial synthetic prospect personas for self-play.

Per the PRD decision, we test against *adversarial* personas, not compliant
synthetic leads — compliant leads inflate the win rate. Each persona is a
deterministic scripted responder so self-play runs are reproducible in CI; an
LLM-backed persona can be swapped in behind the same ``reply`` interface for
richer simulation when a key is present.
"""

from __future__ import annotations

from typing import ClassVar

from salesflow.agent.agent import AgentAction
from salesflow.domain.models import ConversationState, Phase

# A realistic, objection-free field profile shared as a base; personas tweak it.
_BASE_PROFILE: dict[str, str] = {
    "student_name": "Sam",
    "grade_level": "7th grade",
    "subjects": "algebra",
    "performance_level": "around a C right now",
    "parent_contact": "parent@example.com",
    "urgency": "within the next month",
    "prior_tutoring": "no, this would be the first time",
    "test_deadline": "a state math exam in May",
    "schedule_windows": "weekday evenings",
    "decision_maker": "mostly just me",
    "budget_signal": "we set aside about 200 a month",
}


class Persona:
    """Base scripted prospect. Subclasses override :meth:`react`."""

    name: str = "Persona"
    difficulty: str = "low"

    def __init__(self, profile: dict[str, str] | None = None) -> None:
        self.profile = dict(_BASE_PROFILE)
        if profile:
            self.profile.update(profile)
        self.turn = 0
        self._raised: list[str] = []

    def reply(self, action: AgentAction, state: ConversationState) -> str:
        self.turn += 1
        if action.asked_field:
            return self.profile.get(action.asked_field, "I'm not sure")
        return self.react(action, state)

    def react(self, action: AgentAction, state: ConversationState) -> str:
        return "Okay."


class ReadyRita(Persona):
    """High intent, few objections, full info. Converts cleanly."""

    name = "Ready Rita"
    difficulty = "low"

    def react(self, action: AgentAction, state: ConversationState) -> str:
        if action.phase == Phase.WARMUP:
            return "Yes, now is a great time — I've been hoping to find help."
        if action.phase in (Phase.PIVOT_TO_CLOSE, Phase.QUALIFICATION):
            return "Yes, sign me up — let's get started this week."
        return "Sounds good to me."


class HesitantHenry(Persona):
    """Interested but unsure on timing and price; converts after A-R-C."""

    name = "Hesitant Henry"
    difficulty = "medium"

    def react(self, action: AgentAction, state: ConversationState) -> str:
        if action.phase == Phase.WARMUP:
            return "Sure, I have a few minutes I suppose."
        pending = [o for o in ("timing", "price") if o not in self._raised]
        if pending:
            obj = pending[0]
            self._raised.append(obj)
            if obj == "timing":
                return "I'm interested, but honestly it might not be a good time right now."
            return "It also sounds a little expensive for our budget."
        return "Okay, that actually makes sense. Let's do it."


class PushbackPaula(Persona):
    """Raises competitor and price objections, then demands a steep discount."""

    name = "Pushback Paula"
    difficulty = "high"

    def react(self, action: AgentAction, state: ConversationState) -> str:
        if action.phase == Phase.WARMUP:
            return "I'll listen, but I'm already looking at other options."
        steps = [o for o in ("competitor", "discount") if o not in self._raised]
        if steps:
            step = steps[0]
            self._raised.append(step)
            if step == "competitor":
                return "I'm also looking at another company that seems cheaper."
            return "Can you give me a discount, like 25% off the price?"
        return "Hmm, I'll think about it."


class DisqualifierDan(Persona):
    """Self-disqualifies early; exercises graceful-exit logic."""

    name = "Disqualifier Dan"
    difficulty = "high"

    def react(self, action: AgentAction, state: ConversationState) -> str:
        if action.phase == Phase.WARMUP:
            return "Actually, I'm not interested — we don't need any tutoring."
        return "No thanks, please take me off your list."


class SilentSam(Persona):
    """Minimal responses; the agent must probe. Gives no positive signal."""

    name = "Silent Sam"
    difficulty = "medium"

    _TERSE: ClassVar[dict[str, str]] = {
        "student_name": "Sam",
        "grade_level": "7th",
        "subjects": "math",
        "performance_level": "okay I guess",
        "parent_contact": "sam@example.com",
        "urgency": "sometime soon",
        "prior_tutoring": "no",
        "test_deadline": "not sure",
        "schedule_windows": "whenever",
        "decision_maker": "me",
        "budget_signal": "not sure",
    }

    def __init__(self, profile: dict[str, str] | None = None) -> None:
        super().__init__(profile)
        self.profile.update(self._TERSE)

    def react(self, action: AgentAction, state: ConversationState) -> str:
        if action.phase == Phase.WARMUP:
            return "yeah ok"
        return "mm, maybe"


ALL_PERSONAS: list[type[Persona]] = [
    ReadyRita,
    HesitantHenry,
    PushbackPaula,
    DisqualifierDan,
    SilentSam,
]
