"""Aggregates the observability + experiment data the dashboard renders.

Pure data assembly (no web concern) so it is unit-testable. The synthetic
baseline (5 adversarial personas) is always included so the dashboard is
useful from the moment the server starts; if real (live) calls have happened
on this server, they are summarised alongside as "Your calls" so the dashboard
reflects what *you* did, not just the eval suite.
"""

from __future__ import annotations

from salesflow import AGENT_VERSION
from salesflow.domain.models import CallLog
from salesflow.eval.ab import default_price_variants, run_ab
from salesflow.eval.harness import run_suite
from salesflow.eval.judge import GroundingJudge
from salesflow.eval.scorers import score_calls
from salesflow.observability import to_dict


def _calls_summary(logs: list[CallLog]) -> list[dict[str, object]]:
    return [
        {
            "session_id": c.session_id,
            "outcome": c.outcome.value,
            "final_phase": c.final_phase.value,
            "escalation_trigger": (
                c.escalation_trigger.value if c.escalation_trigger else None
            ),
            "turns": len(c.turns),
            "collected_fields": list(c.collected_fields),
        }
        for c in logs
    ]


def _block(logs: list[CallLog], *, label: str) -> dict[str, object]:
    if not logs:
        return {"label": label, "n_calls": 0, "kpis": None, "calls": [], "sample_transcript": None}
    return {
        "label": label,
        "n_calls": len(logs),
        "kpis": score_calls(logs).as_dict(),
        "calls": _calls_summary(logs),
        "sample_transcript": to_dict(logs[-1], redact=True),
    }


def build_dashboard(
    n_ab: int = 300,
    seed: int = 7,
    live_calls: list[CallLog] | None = None,
) -> dict[str, object]:
    synthetic = run_suite()
    live = list(live_calls or [])
    judge = GroundingJudge()
    ab = run_ab(default_price_variants(), n_per_variant=n_ab, seed=seed)

    return {
        "agent_version": AGENT_VERSION,
        # Headline block — what the user actually wants to see updating: their calls.
        "live": _block(live, label="Your live calls"),
        # Always-present baseline so the dashboard is non-empty at startup.
        "synthetic": _block(synthetic, label="Synthetic baseline (5 adversarial personas)"),
        "hallucination_rate": judge.hallucination_rate(synthetic + live),
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
        # Back-compat top-level fields so the older Dashboard.jsx still reads ok.
        "kpis": score_calls(synthetic).as_dict(),
        "calls": _calls_summary(synthetic),
        "sample_transcript": to_dict(synthetic[0], redact=True),
    }
