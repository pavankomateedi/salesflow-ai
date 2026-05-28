"""A/B experiment runner for the recursive-improvement loop.

Runs playbook variants against a population of adversarial price-objection
prospects in self-play, measures objection-to-close per variant, and reports the
lift over baseline with a two-proportion z-test (PRD: "before/after KPI evidence
with statistical significance notation").

The simulated world encodes each variant's *true* persuasiveness, which the
agent does not see — the experiment's job is to recover it from outcomes, the
same way a real canary A/B would. Deterministic given a seed.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from salesflow.agent.agent import AgentAction, Playbook, SalesAgent
from salesflow.domain.models import ConversationState, Lead, Outcome, Phase
from salesflow.eval.harness import MAX_TURNS
from salesflow.knowledge.kb import ObjectionType
from salesflow.personas import Persona


@dataclass
class Variant:
    """A promotable playbook plus the world's hidden true persuasiveness."""

    name: str
    playbook: Playbook
    true_persuasiveness: float  # ground truth, unknown to the agent


class StochasticPriceProspect(Persona):
    """Raises a price objection, then converts ~Bernoulli(accept_prob).

    ``accept_prob`` is supplied by the experiment world (the variant's true
    persuasiveness), so a better rebuttal genuinely converts more often.
    """

    name = "Price Prospect"
    difficulty = "high"

    def __init__(self, accept_prob: float, rng: random.Random) -> None:
        super().__init__()
        self._accept_prob = accept_prob
        self._rng = rng
        self._raised_price = False
        self._decided: bool | None = None

    def react(self, action: AgentAction, state: ConversationState) -> str:
        if action.phase == Phase.WARMUP:
            return "Okay, I can talk for a bit."
        if not self._raised_price:
            self._raised_price = True
            return "Honestly, that sounds too expensive for us right now."
        if self._decided is None:
            self._decided = self._rng.random() < self._accept_prob
        if self._decided:
            return "Okay, you've convinced me — let's do it."
        return "I'll think about it, thanks."


def _objection_to_close(variant: Variant, n: int, rng: random.Random) -> tuple[int, int]:
    """Run ``n`` self-play calls; return (closes, total)."""
    closes = 0
    for i in range(n):
        agent = SalesAgent(playbook=variant.playbook)
        prospect = StochasticPriceProspect(variant.true_persuasiveness, rng)
        state = ConversationState(lead=Lead(phone=f"+1555{i:07d}"))
        action = agent.open(state)
        turns = 0
        while not state.phase.is_terminal and turns < MAX_TURNS:
            action = agent.respond(state, prospect.reply(action, state))
            turns += 1
        if state.outcome == Outcome.CLOSED_WON:
            closes += 1
    return closes, n


def _two_proportion_p(c1: int, n1: int, c2: int, n2: int) -> float:
    """Two-sided p-value for a difference in two proportions (normal approx)."""
    if n1 == 0 or n2 == 0:
        return 1.0
    p1, p2 = c1 / n1, c2 / n2
    pool = (c1 + c2) / (n1 + n2)
    denom = math.sqrt(pool * (1 - pool) * (1 / n1 + 1 / n2))
    if denom == 0:
        return 1.0
    z = (p1 - p2) / denom
    return math.erfc(abs(z) / math.sqrt(2))  # two-sided


@dataclass
class VariantResult:
    name: str
    closes: int
    n: int
    rate: float
    lift_vs_baseline: float
    p_value: float
    significant: bool


@dataclass
class ABReport:
    baseline: str
    results: list[VariantResult] = field(default_factory=list)

    def best(self) -> VariantResult:
        return max(self.results, key=lambda r: r.rate)


def run_ab(
    variants: list[Variant],
    *,
    n_per_variant: int = 200,
    seed: int = 7,
    alpha: float = 0.05,
) -> ABReport:
    """Run the experiment; first variant is treated as the baseline."""
    rng = random.Random(seed)
    raw = {v.name: _objection_to_close(v, n_per_variant, rng) for v in variants}
    baseline = variants[0]
    b_close, b_n = raw[baseline.name]
    b_rate = b_close / b_n if b_n else 0.0

    report = ABReport(baseline=baseline.name)
    for v in variants:
        closes, n = raw[v.name]
        rate = closes / n if n else 0.0
        if v.name == baseline.name:
            p_value, significant, lift = 1.0, False, 0.0
        else:
            p_value = _two_proportion_p(closes, n, b_close, b_n)
            significant = p_value < alpha
            lift = rate - b_rate
        report.results.append(
            VariantResult(v.name, closes, n, rate, lift, p_value, significant)
        )
    return report


def default_price_variants() -> list[Variant]:
    """Baseline + the 3 price-objection variants from the PRD sprint plan."""
    return [
        Variant("baseline", Playbook(name="baseline"), true_persuasiveness=0.30),
        Variant(
            "roi_framing",
            Playbook(
                name="roi_framing",
                objection_overrides={
                    ObjectionType.PRICE: (
                        "I hear you. Families tell us the jump in their student's grades is "
                        "worth far more than the hourly cost — and it's month-to-month with a "
                        "refundable first session. Want to start light and scale up?"
                    )
                },
            ),
            true_persuasiveness=0.45,
        ),
        Variant(
            "smaller_entry",
            Playbook(
                name="smaller_entry",
                objection_overrides={
                    ObjectionType.PRICE: (
                        "Totally fair. Many families start with just one Starter session a week "
                        "to keep it light, then add hours once they see progress. Shall we try "
                        "a single session first?"
                    )
                },
            ),
            true_persuasiveness=0.50,
        ),
        Variant(
            "social_proof",
            Playbook(
                name="social_proof",
                objection_overrides={
                    ObjectionType.PRICE: (
                        "I understand. Most families in your area start on Standard and stay "
                        "because they see results within a month — and there's no contract. "
                        "Would it help to begin before the next test?"
                    )
                },
            ),
            true_persuasiveness=0.38,
        ),
    ]
