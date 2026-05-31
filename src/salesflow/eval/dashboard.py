"""Aggregates the observability + experiment data the dashboard renders.

The synthetic baseline (5 adversarial personas + A/B price experiment) is
deterministic by ``(n_ab, seed)`` and expensive to compute, so the synthetic
block is built separately and is safe to cache by the caller. The live block
(real calls captured on the server) must always be request-fresh and is not
cached.

The web layer calls :func:`synthetic_block` (memoised by ``n_ab``) once per
``n_ab`` value, then merges with :func:`live_block` on every request.
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


def synthetic_block(n_ab: int = 300, seed: int = 7) -> dict[str, object]:
    """The deterministic, cacheable part: self-play KPIs + A/B + grounding judge.

    Safe to memoise by ``(n_ab, seed)``. Does NOT include live calls.
    """
    synthetic = run_suite()
    ab = run_ab(default_price_variants(), n_per_variant=n_ab, seed=seed)
    return {
        "agent_version": AGENT_VERSION,
        "synthetic": _block(synthetic, label="Synthetic baseline (5 adversarial personas)"),
        "synthetic_hallucination_rate": GroundingJudge().hallucination_rate(synthetic),
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
    }


def live_block(live_calls: list[CallLog]) -> dict[str, object]:
    """The request-fresh part: KPIs over the calls captured on this server."""
    live = list(live_calls or [])
    return {
        "live": _block(live, label="Your live calls"),
        "live_hallucination_rate": GroundingJudge().hallucination_rate(live) if live else 0.0,
    }


def build_dashboard(
    n_ab: int = 300,
    seed: int = 7,
    live_calls: list[CallLog] | None = None,
) -> dict[str, object]:
    """Compose synthetic + live blocks. Kept for tests and back-compat callers
    that don't need caching control. Production uses ``synthetic_block`` directly
    so the heavy half can be memoised."""
    synth = synthetic_block(n_ab=n_ab, seed=seed)
    live = live_block(live_calls or [])
    return {
        **synth,
        **live,
        # Convenience for the React layer: a combined hallucination_rate
        # judged over synthetic + live so a misbehaving live call shows up
        # even when synthetic stays at 0.
        "hallucination_rate": GroundingJudge().hallucination_rate(
            run_suite() + (live_calls or [])
        ),
    }
