"""The SalesAgent orchestrator.

Ties the deterministic decisioning modules together into one auditable turn
function: ``respond(state, prospect_text)`` analyses the utterance, updates
signals, runs escalation -> disqualification -> objection -> phase logic in
priority order, and returns a single :class:`AgentAction` with a full decision
trace. Policy/pricing answers are grounded (KB + structured config); the LLM is
an optional phrasing layer that rewrites the planned line in context (kept
*after* the deterministic decision, with hard constraints against inventing
new facts).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from salesflow import analysis
from salesflow.agent.escalation import classify_escalation
from salesflow.agent.pivot import pivot_ready
from salesflow.agent.question_selector import QUESTIONS, next_field
from salesflow.config import SETTINGS, Settings
from salesflow.domain.models import (
    ConversationState,
    EscalationTrigger,
    Outcome,
    Phase,
    Sentiment,
    Turn,
)
from salesflow.knowledge.kb import KnowledgeBase, ObjectionType, classify_objection
from salesflow.llm import MockLLMClient
from salesflow.llm.base import LLMClient, Message

_PRICING_INTENT = (
    "how much", "price", "pricing", "cost", "rate", "per hour", "per session", "plans",
)
_POLICY_INTENT = (
    "cancel", "cancellation", "refund", "contract", "recording", "privacy",
    "guarantee", "reschedule", "match", "subjects", "grades", "ferpa", "data",
)
# Competitive questions -> grounded battlecard retrieval (competitive.md). A
# question naming a competitor ("Wyzant") is still caught as a COMPETITOR
# objection first; these cues catch the neutral "how are you different" framing.
_COMPETITIVE_INTENT = (
    "different from", "difference between", "how are you different", "compare",
    "comparison", "better than", "versus", " vs ", "what makes you", "why should i",
    "why nerdy", "stand out", "other services", "other tutoring", "self-service",
    "in-person", "in person", "local tutor", "local tutoring", "another service",
)
# Warm sign-off appended to every terminal utterance (close / escalation /
# graceful exit) so every call ends with the same closer regardless of outcome.
CLOSING_THANKS = "Many thanks for your time today and speak to you soon!"

# Specific facts we deliberately do not hold; a question hitting these escalates
# as low-confidence rather than being answered from a loosely-matching chunk.
_OUT_OF_SCOPE = (
    "license", "certification", "credential", "accredited", "lawsuit",
    "ceo", "revenue", "social security", "ssn",
)


@dataclass
class Playbook:
    """A promotable conversation strategy. The A/B runner swaps these.

    ``questions`` overrides default field phrasings; ``objection_overrides``
    swaps a rendered rebuttal for a given objection (e.g. ROI-framing vs
    social-proof price variants).
    """

    name: str = "baseline"
    questions: dict[str, str] = field(default_factory=lambda: dict(QUESTIONS))
    objection_overrides: dict[ObjectionType, str] = field(default_factory=dict)


@dataclass
class AgentAction:
    """One agent turn plus its decision trace (for transcripts + auditing)."""

    utterance: str
    phase: Phase
    asked_field: str | None = None
    objection: ObjectionType | None = None
    escalation: EscalationTrigger | None = None
    grounded_sources: list[str] = field(default_factory=list)
    decision: dict[str, object] = field(default_factory=dict)


class SalesAgent:
    def __init__(
        self,
        kb: KnowledgeBase | None = None,
        *,
        settings: Settings = SETTINGS,
        playbook: Playbook | None = None,
        version: str = "vani-v1.0.0",
        llm: LLMClient | None = None,
    ) -> None:
        self.kb = kb or KnowledgeBase()
        self.settings = settings
        self.playbook = playbook or Playbook()
        self.version = version
        # Tests + CI use mock (deterministic). The web/voice surfaces opt into the
        # live backend by passing ``llm=get_client()``.
        self.llm: LLMClient = llm or MockLLMClient()

    # -- public API ---------------------------------------------------------

    def open(self, state: ConversationState) -> AgentAction:
        """The first agent turn: recording disclosure + warm identity confirm."""
        greeting = (
            self.settings.recording_disclosure
            + "I'm reaching out about tutoring support — is now an okay time to chat?"
        )
        action = AgentAction(utterance=greeting, phase=Phase.WARMUP, decision={"step": "open"})
        self._record(state, action)
        return action

    def respond(self, state: ConversationState, prospect_text: str) -> AgentAction:
        """Produce the next agent action given a prospect utterance."""
        self._ingest_prospect_turn(state, prospect_text)

        sentiment = analysis.score_sentiment(prospect_text)
        self._update_signals(state, prospect_text, sentiment)

        # Resolve any grounded answer the prospect's question demands.
        answer, sources, policy_unanswerable = self._grounded_answer(prospect_text)

        # 1) Escalation has top priority.
        esc = classify_escalation(
            state,
            prospect_text,
            settings=self.settings,
            policy_question_unanswerable=policy_unanswerable,
        )
        if esc is not None:
            return self._escalate(state, esc.trigger, esc.reason)

        # 2) Clear self-disqualification -> graceful exit.
        if analysis.is_disqualifying(prospect_text):
            return self._graceful_exit(state)

        # 3) Objection handling (A-R-C).
        objection = classify_objection(prospect_text)
        if objection is not None:
            return self._handle_objection(state, objection)

        # 4) Normal phase progression (optionally prefixing a grounded answer).
        return self._advance(state, prefix=answer, sources=sources)

    # -- internals ----------------------------------------------------------

    def _ingest_prospect_turn(self, state: ConversationState, text: str) -> None:
        # Record the field we were waiting on as collected, unless this turn is
        # really an objection or a disqualification rather than an answer.
        last_asked = state.asked_fields[-1] if state.asked_fields else None
        if (
            last_asked
            and not state.lead.is_known(last_asked)
            and classify_objection(text) is None
            and not analysis.is_disqualifying(text)
        ):
            value = self._extract_field_value(last_asked, text)
            if value:
                state.lead.collected[last_asked] = value
        state.add_turn(
            Turn(speaker="prospect", text=text, phase=state.phase,
                 sentiment=analysis.score_sentiment(text))
        )

    def _extract_field_value(self, field: str, text: str) -> str | None:
        """Pull the canonical value for ``field`` out of the parent's reply.

        Voice-transcribed replies are noisy: filler ("um", "mm-hmm"), self-
        corrections ("not Mr. B, it's Mr. V"), and off-topic asides routinely
        end up where a clean value belongs. With a live LLM we ask it to
        extract just the value (or return ``NO_ANSWER`` for filler so the field
        stays empty and the agent re-asks). With the mock backend we keep the
        original naive behavior so the test suite stays deterministic.
        """
        if self.llm.name == "mock":
            return analysis.extracts_field(field, text)
        try:
            system = (
                "You extract a single structured field value from a parent's spoken "
                "reply during a tutoring sales call. The reply may include filler "
                "('um', 'mm-hmm', 'yeah'), self-corrections (\"not X, it's Y\"), or "
                "off-topic asides. Extract ONLY the canonical value for the requested "
                "field, in its minimal natural form (e.g. 'Mr. V', '8th grade', "
                "'math and chemistry', 'STAR test in April', 'pavan@example.com'). "
                "If the parent did NOT actually answer (only filler or unrelated), "
                "reply with the literal string NO_ANSWER. Output ONLY the value or "
                "NO_ANSWER — no quotes, no prefix, no punctuation around it."
            )
            user = (
                f"Field being asked: {field}\n"
                f"Parent reply: {text!r}\n"
                "Canonical value:"
            )
            resp = self.llm.complete(
                system=system,
                messages=[Message(role="user", content=user)],
                max_tokens=60,
                temperature=0.0,
            )
            value = resp.text.strip().strip('"').strip("'").rstrip(".").strip()
            if not value or value.upper() == "NO_ANSWER":
                return None
            # Grounding check: the LLM must extract a value that actually appears
            # in (or is recognisably derived from) the parent's reply. Otherwise
            # it's a hallucination and we fall back to the deterministic extractor
            # so collected_fields stays grounded in what was actually said. We
            # compare on lowercased token overlap so minor normalisation
            # ("8th grade" from "eighth grade") survives.
            value_tokens = set(re.findall(r"[a-z0-9]+", value.lower()))
            text_tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
            if value_tokens and not (value_tokens & text_tokens):
                return analysis.extracts_field(field, text)
            return value
        except Exception:
            return analysis.extracts_field(field, text)

    def _update_signals(
        self, state: ConversationState, text: str, sentiment: Sentiment
    ) -> None:
        if sentiment == Sentiment.NEGATIVE:
            state.negative_streak += 1
        else:
            state.negative_streak = 0
        if analysis.is_positive_intent(text) or sentiment == Sentiment.POSITIVE:
            state.positive_signals += 1
        if analysis.is_disqualifying(text):
            state.disqualify_signals += 1

    def _grounded_answer(self, text: str) -> tuple[str | None, list[str], bool]:
        low = text.lower()
        is_question = "?" in text
        # Pricing answers come from structured config, never the LLM/KB prose.
        if any(cue in low for cue in _PRICING_INTENT):
            plans = self.settings.pricing.plans
            answer = (
                "Our plans are month-to-month: Starter at ${starter}/hour, "
                "Standard at ${standard}/hour, and Intensive at ${intensive}/hour."
            ).format(**plans)
            return answer, ["pricing-config"], False
        # Specific facts we don't hold -> low-confidence escalation, never a guess.
        if is_question and any(cue in low for cue in _OUT_OF_SCOPE):
            return None, [], True
        # Policy questions: retrieval-only.
        if is_question and any(cue in low for cue in _POLICY_INTENT):
            chunks = self.kb.retrieve(text, k=1)
            if chunks:
                top = chunks[0]
                return top.body, [top.source], False
            return None, [], True  # unanswerable policy question -> escalate
        # Competitive questions: grounded battlecard retrieval. Soft — a miss just
        # proceeds (no escalation), since a differentiation question is not a
        # high-stakes factual gap the way an unanswerable policy question is.
        if is_question and any(cue in low for cue in _COMPETITIVE_INTENT):
            comp = [c for c in self.kb.retrieve(text, k=3) if c.source == "competitive"]
            if comp:
                return comp[0].body, ["competitive"], False
            return None, [], False
        return None, [], False

    def _advance(
        self, state: ConversationState, *, prefix: str | None, sources: list[str]
    ) -> AgentAction:
        if state.phase == Phase.WARMUP:
            state.phase = Phase.DISCOVERY

        nf = next_field(state.lead, state.asked_fields)
        if nf is not None:
            # We are still gathering fields: discovery (required) or qualification (leading).
            if state.lead.discovery_complete():
                state.phase = Phase.QUALIFICATION
            elif state.phase not in (Phase.DISCOVERY, Phase.QUALIFICATION):
                state.phase = Phase.DISCOVERY
            state.asked_fields.append(nf)
            question = self.playbook.questions.get(nf, QUESTIONS[nf])
            utterance = f"{prefix} {question}".strip() if prefix else question
            action = AgentAction(
                utterance=utterance,
                phase=state.phase,
                asked_field=nf,
                grounded_sources=sources,
                decision={"step": "ask_field", "field": nf},
            )
            self._record(state, action)
            return action

        # All scripted fields gathered — try to pivot.
        pivot = pivot_ready(state, self.settings)
        if pivot.ready or state.phase == Phase.PIVOT_TO_CLOSE:
            return self._pivot_or_close(state, pivot_signals=pivot.as_dict(), prefix=prefix)

        # If we've already probed once and the parent just gave a positive reply
        # ("Yes.", "Yes, it does.", "sounds good"), commit to the pivot instead
        # of looping the same probe. The strict pivot_ready check can fail when
        # a leading field has a soft value (e.g., the LLM extracted "yes" rather
        # than "soon"), but the parent's intent is unmistakable.
        last_prospect = state.prospect_turns[-1].text if state.prospect_turns else ""
        # Use the TIGHT close-affirmation check, NOT raw positive sentiment —
        # "really love it but the cost is too high" reads as POSITIVE sentiment
        # but is a price objection. The same broad check broke A/B in an
        # earlier round; do not bring it back.
        positive_reply = (
            analysis.is_positive_intent(last_prospect)
            or analysis.is_close_affirmation(last_prospect)
        )
        if state.phase == Phase.QUALIFICATION and state.probe_attempts > 0 and positive_reply:
            return self._pivot_or_close(state, pivot_signals=pivot.as_dict(), prefix=prefix)

        # Not ready: vary the soft fit-confirmation probe by attempt so it
        # doesn't read as a broken-record loop.
        state.phase = Phase.QUALIFICATION
        state.probe_attempts += 1
        probes = (
            "Based on what you've shared, this sounds like a strong fit. "
            "Does getting started this week sound good to you?",
            "Just to make sure I'm not missing anything — is there anything else "
            "you'd want to know before we schedule the first session?",
            "Would picking a time later this week be easier, or earlier in the next?",
        )
        probe = probes[min(state.probe_attempts - 1, len(probes) - 1)]
        utterance = f"{prefix} {probe}".strip() if prefix else probe
        action = AgentAction(
            utterance=utterance,
            phase=Phase.QUALIFICATION,
            grounded_sources=sources,
            decision={"step": "qualify_probe", "attempt": state.probe_attempts,
                      "pivot": pivot.as_dict()},
        )
        self._record(state, action)
        return action

    def _pivot_or_close(
        self, state: ConversationState, *, pivot_signals: dict[str, bool], prefix: str | None
    ) -> AgentAction:
        last_prospect = state.prospect_turns[-1].text if state.prospect_turns else ""
        already_pivoted = state.phase == Phase.PIVOT_TO_CLOSE

        # If we already pivoted and the prospect agreed, close. Accept BOTH the
        # specific positive-intent phrases (e.g., "sign me up", "let's do it")
        # AND tight close-affirmations ("Yes.", "Sure.", "Okay yeah") — but NOT
        # generic positive sentiment, because polite rejections like "I'll think
        # about it, thanks." would otherwise close the call.
        positive_reply = (
            analysis.is_positive_intent(last_prospect)
            or analysis.is_close_affirmation(last_prospect)
        )
        if already_pivoted and positive_reply:
            state.phase = Phase.CLOSE
            state.outcome = Outcome.CLOSED_WON
            action = AgentAction(
                utterance=(
                    "Wonderful — I'll get your tutor match started and send a confirmation "
                    "to your contact on file. You'll hear from us within 48 hours. "
                    + CLOSING_THANKS
                ),
                phase=Phase.CLOSE,
                decision={"step": "close", "pivot": pivot_signals},
            )
            self._record(state, action)
            return action

        state.phase = Phase.PIVOT_TO_CLOSE
        short_close = "Shall we get the first session scheduled?"

        # First entry into PIVOT_TO_CLOSE -> the full recap. Subsequent turns must
        # NOT re-recap (was annoying users who asked grounded follow-up questions
        # like "How are you different from a local tutor?" and got the full recap
        # appended to every reply).
        if not already_pivoted:
            summary = self._build_recap(state)
            utterance = f"{prefix} {summary}".strip() if prefix else summary
            action = AgentAction(
                utterance=utterance,
                phase=Phase.PIVOT_TO_CLOSE,
                decision={"step": "pivot", "pivot": pivot_signals},
            )
            self._record(state, action)
            return action

        # Re-pivot path: prospect engaged with a follow-up after the recap.
        # If they asked a grounded question (prefix is set), surface the answer
        # plus a short close. ALSO increment probe_attempts — repeatedly asking
        # follow-ups without committing IS unproductive activity and the Silent
        # Sam invariant requires it to escalate as disqualification-uncertainty
        # eventually. Previously this path skipped the increment and the loop
        # ran to MAX_TURNS.
        if prefix:
            state.probe_attempts += 1
            utterance = f"{prefix} {short_close}".strip()
            action = AgentAction(
                utterance=utterance,
                phase=Phase.PIVOT_TO_CLOSE,
                decision={"step": "answer_then_close", "pivot": pivot_signals},
            )
            self._record(state, action)
            return action

        state.probe_attempts += 1
        action = AgentAction(
            utterance=(
                "Based on what you've shared, this sounds like a strong fit. " + short_close
            ),
            phase=Phase.PIVOT_TO_CLOSE,
            decision={"step": "re_pivot", "pivot": pivot_signals},
        )
        self._record(state, action)
        return action

    def _handle_objection(self, state: ConversationState, objection: ObjectionType) -> AgentAction:
        state.phase = Phase.OBJECTION_HANDLING
        if objection.value not in state.open_objections:
            state.open_objections.append(objection.value)
        override = self.playbook.objection_overrides.get(objection)
        rebuttal = self.kb.rebuttal(objection)
        fallback = "I understand — let me address that."
        text = override or (rebuttal.render() if rebuttal else fallback)
        # A-R-C closes by re-engaging; treat the objection as handled and clear it
        # so a resolved objection no longer blocks pivot (recurrence -> probes/escalation).
        if objection.value in state.open_objections:
            state.open_objections.remove(objection.value)
        if objection.value not in state.resolved_objections:
            state.resolved_objections.append(objection.value)
        action = AgentAction(
            utterance=text,
            phase=Phase.OBJECTION_HANDLING,
            objection=objection,
            grounded_sources=["objections"] if not override else ["objections", "variant"],
            decision={"step": "objection", "type": objection.value, "variant": bool(override)},
        )
        self._record(state, action)
        return action

    def _escalate(
        self, state: ConversationState, trigger: EscalationTrigger, reason: str
    ) -> AgentAction:
        state.phase = Phase.ESCALATION
        state.outcome = Outcome.ESCALATED
        state.escalation_trigger = trigger
        action = AgentAction(
            utterance=(
                "Let me get you to a specialist who can give you the most accurate help — "
                "I'm connecting you now and passing along everything we've discussed. "
                + CLOSING_THANKS
            ),
            phase=Phase.ESCALATION,
            escalation=trigger,
            decision={"step": "escalate", "trigger": trigger.value, "reason": reason},
        )
        self._record(state, action)
        return action

    def _graceful_exit(self, state: ConversationState) -> AgentAction:
        state.phase = Phase.GRACEFUL_EXIT
        state.outcome = Outcome.GRACEFUL_EXIT
        action = AgentAction(
            utterance=(
                "Totally understand. May we reach out in the future if things change? "
                + CLOSING_THANKS
            ),
            phase=Phase.GRACEFUL_EXIT,
            decision={"step": "graceful_exit"},
        )
        self._record(state, action)
        return action

    def _build_recap(self, state: ConversationState) -> str:
        """Build the pivot recap.

        Two-stage: a deterministic template assembles the collected facts (so
        the recap is always grounded), then — when a live LLM is available —
        an "LLM review" pass rewrites it into a single, natural paragraph that
        feels human rather than a fill-in-the-blanks summary. Guardrails reject
        the LLM rewrite if it drops the closing question or invents a ``$NN``
        figure that wasn't in the facts.
        """
        template = self._build_recap_template(state)
        if self.llm.name == "mock":
            return template
        try:
            facts = "\n".join(
                f"- {k}: {v}" for k, v in state.lead.all_fields.items() if v
            )
            recent = "\n".join(
                f"  {t.speaker}: {t.text}" for t in state.turns[-6:]
            )
            system = (
                "You are Vani, a warm tutoring sales rep at Nerdy, about to ask "
                "the parent to commit to scheduling the first session. Produce a "
                "single short paragraph (2-3 sentences) that:\n"
                "1. Briefly summarises the parent's situation using ONLY the facts "
                "below. Do NOT invent any facts, names, grades, subjects, or "
                "details that are not in the facts list.\n"
                "2. Reassures with the standing offer: month-to-month, refundable "
                "first session, and a matched tutor within 48 hours.\n"
                "3. Ends with ONE closing question that asks to schedule the first "
                "session.\n"
                "Tone: warm, calm, concise. No bullet points. No dollar figures."
            )
            user = (
                f"Collected facts:\n{facts or '- (no facts collected)'}\n\n"
                f"Last few turns of the call:\n{recent}\n\n"
                f"Fallback template (only use as a structural guide): {template}\n\n"
                "Your recap:"
            )
            resp = self.llm.complete(
                system=system,
                messages=[Message(role="user", content=user)],
                max_tokens=200,
                temperature=0.4,
            )
            text = resp.text.strip().strip('"').strip("'")
            # Guardrails: must end with a closing question; recap must not invent
            # dollar figures (pricing is handled separately, never in the recap).
            # `[\d,]+` matches both plain and comma-grouped figures.
            if "?" not in text or re.search(r"\$[\d,]+", text):
                return template
            return text or template
        except Exception:
            return template

    def _build_recap_template(self, state: ConversationState) -> str:
        f = state.lead.all_fields
        name = f.get("student_name") or "your student"
        parts: list[str] = [f"tutoring for {name}"]
        if f.get("grade_level"):
            parts.append(f"in {f['grade_level']}")
        if f.get("subjects"):
            parts.append(f"focused on {f['subjects']}")
        if f.get("performance_level"):
            parts.append(f"currently at {f['performance_level']}")
        if f.get("urgency"):
            parts.append(f"timeline: {f['urgency']}")
        recap = ", ".join(parts)
        return (
            f"So to recap — {recap}. We'd start month-to-month with a refundable "
            "first session and a matched tutor within 48 hours. "
            "Shall we get the first session scheduled?"
        )

    def _naturalize(
        self, base: str, state: ConversationState, asked_field: str | None
    ) -> str:
        """Rewrite a planned line conversationally, in Vani's voice.

        Constraints kept hard so the LLM cannot drift off grounded facts:
          * Any ``$NN`` figure in the planned line must remain in the rewrite
            verbatim (we revert otherwise).
          * The mock backend is a no-op so the test suite stays deterministic.
        """
        if self.llm.name == "mock":
            return base
        last_prospect = state.prospect_turns[-1].text if state.prospect_turns else ""
        if not last_prospect:  # opening greeting has no context yet
            return base
        try:
            system = (
                "You are Vani, a warm and professional tutoring sales rep at Nerdy. "
                "Rewrite the agent's planned next line so it sounds natural and "
                "conversational, briefly acknowledging what the parent just said when "
                "relevant. One or two sentences max, calm and human. "
                "CRITICAL: Keep ALL dollar figures, percentages, and specific policy "
                "facts EXACTLY as written. Do NOT invent any pricing, guarantees, or "
                "facts not in the planned line. If the planned line ends with a "
                "question, the rewrite must end with the same question."
            )
            user = (
                f"Parent just said: {last_prospect!r}\n"
                f"Planned agent line: {base!r}\n"
                f"Asking about next: {asked_field or 'n/a'}\n\n"
                "Your rewrite (one or two sentences):"
            )
            resp = self.llm.complete(
                system=system,
                messages=[Message(role="user", content=user)],
                max_tokens=180,
                temperature=0.4,
            )
            rewritten = resp.text.strip().strip('"').strip("'")
            # Defensive grounding check: any $-figure in the planned line MUST
            # appear verbatim in the rewrite. Pattern matches plain ($90), decimal
            # ($90.00), and comma-grouped ($1,200) figures so the guard still
            # holds when a Pricing tier exceeds $999.
            for dollar in re.findall(r"\$[\d,]+(?:\.\d+)?", base):
                if dollar not in rewritten:
                    return base
            return rewritten or base
        except Exception:
            # An LLM hiccup must never break the call; fall back to the planned line.
            return base

    def _record(self, state: ConversationState, action: AgentAction) -> None:
        # Skip naturalize on the pivot recap turn — _build_recap already ran the
        # LLM review pass on it, and a second pass against a different (shorter)
        # prompt can drop the closing question or paraphrase facts away. The
        # close turn (step="close") has hardcoded English that is fine to rephrase.
        if action.decision.get("step") != "pivot":
            action.utterance = self._naturalize(action.utterance, state, action.asked_field)
        state.add_turn(
            Turn(
                speaker="agent",
                text=action.utterance,
                phase=action.phase,
                decision=action.decision,
            )
        )
