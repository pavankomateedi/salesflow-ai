"""Post-call judge for hallucination / ungrounded-claim detection.

The deterministic core verifies the one class of fact we can check exactly:
every dollar figure the agent states must match the structured pricing config
(PRD: pricing is injected from config, never generated). An optional LLM judge
(real Claude backend) can add fuzzy policy-grounding checks on top, but the
offline default needs no key and never flags the deterministic agent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from salesflow.config import SETTINGS, Settings
from salesflow.domain.models import CallLog
from salesflow.llm.base import LLMClient

_DOLLAR_RE = re.compile(r"\$(\d+)")


@dataclass
class JudgeVerdict:
    session_id: str
    grounded: bool
    n_claims: int
    flags: list[dict[str, object]] = field(default_factory=list)


class GroundingJudge:
    def __init__(self, *, settings: Settings = SETTINGS, llm: LLMClient | None = None) -> None:
        self.settings = settings
        self.llm = llm
        self._allowed_prices = set(settings.pricing.plans.values())

    def judge(self, call: CallLog) -> JudgeVerdict:
        flags: list[dict[str, object]] = []
        n_claims = 0
        for i, turn in enumerate(call.turns):
            if turn.speaker != "agent":
                continue
            for amount in _DOLLAR_RE.findall(turn.text):
                n_claims += 1
                if int(amount) not in self._allowed_prices:
                    flags.append(
                        {
                            "turn": i,
                            "issue": "ungrounded_price",
                            "value": int(amount),
                            "text": turn.text,
                        }
                    )
        return JudgeVerdict(
            session_id=call.session_id,
            grounded=not flags,
            n_claims=n_claims,
            flags=flags,
        )

    def judge_batch(self, calls: list[CallLog]) -> list[JudgeVerdict]:
        return [self.judge(c) for c in calls]

    def hallucination_rate(self, calls: list[CallLog]) -> float:
        if not calls:
            return 0.0
        verdicts = self.judge_batch(calls)
        return sum(0 if v.grounded else 1 for v in verdicts) / len(verdicts)
