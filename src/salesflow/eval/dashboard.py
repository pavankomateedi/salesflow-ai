"""Aggregates the observability + experiment data the dashboard renders.

Pure data assembly (no web concern) so it is unit-testable: runs the self-play
suite, scores KPIs, computes the grounding (hallucination) rate, runs the A/B
improvement experiment, and attaches one PII-redacted sample transcript with its
per-turn decision trace. The web layer just serialises this to JSON.
"""

from __future__ import annotations

from salesflow import AGENT_VERSION
from salesflow.eval.ab import default_price_variants, run_ab
from salesflow.eval.harness import run_suite
from salesflow.eval.judge import GroundingJudge
from salesflow.eval.scorers import score_calls
from salesflow.observability import to_dict


def build_dashboard(n_ab: int = 300, seed: int = 7) -> dict[str, object]:
    logs = run_suite()
    report = score_calls(logs)
    hallucination = GroundingJudge().hallucination_rate(logs)
    ab = run_ab(default_price_variants(), n_per_variant=n_ab, seed=seed)

    return {
        "agent_version": AGENT_VERSION,
        "kpis": report.as_dict(),
        "hallucination_rate": hallucination,
        "calls": [
            {
                "session_id": c.session_id,
                "outcome": c.outcome.value,
                "final_phase": c.final_phase.value,
                "escalation_trigger": (
                    c.escalation_trigger.value if c.escalation_trigger else None
                ),
                "turns": len(c.turns),
            }
            for c in logs
        ],
        "ab": {
            "baseline": ab.baseline,
            "n_per_variant": n_ab,
            "best": ab.best().name,
            "variants": [
                {
                    "name": r.name,
                    "rate": r.rate,
                    "lift": r.lift_vs_baseline,
                    "p_value": r.p_value,
                    "significant": r.significant,
                }
                for r in ab.results
            ],
        },
        "sample_transcript": to_dict(logs[0], redact=True),
    }
