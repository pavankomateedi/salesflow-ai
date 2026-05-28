"""Command-line entry point for the evaluation harness.

    python -m salesflow.eval.cli suite     # self-play vs all personas + KPIs
    python -m salesflow.eval.cli ab        # A/B price-objection experiment
    python -m salesflow.eval.cli all       # both (default)
"""

from __future__ import annotations

import argparse
from pathlib import Path

from salesflow.eval.ab import default_price_variants, run_ab
from salesflow.eval.harness import run_suite
from salesflow.eval.judge import GroundingJudge
from salesflow.eval.scorers import score_calls
from salesflow.observability import save_transcript


def _run_suite(transcript_dir: Path | None) -> None:
    logs = run_suite()
    print("\n=== Self-play vs adversarial personas ===")
    for c in logs:
        esc = c.escalation_trigger.value if c.escalation_trigger else "-"
        print(f"  {c.session_id:24} {c.outcome.value:14} (final={c.final_phase.value}, esc={esc})")
        if transcript_dir:
            save_transcript(c, transcript_dir)

    report = score_calls(logs)
    print("\n=== KPIs ===")
    for k, v in report.as_dict().items():
        if isinstance(v, float):
            print(f"  {k:28}: {v:.3f}")
        else:
            print(f"  {k:28}: {v}")
    print(f"  {'hallucination_rate':28}: {GroundingJudge().hallucination_rate(logs):.3f}")
    if transcript_dir:
        print(f"\nTranscripts written to {transcript_dir}")


def _run_ab(n: int, seed: int) -> None:
    report = run_ab(default_price_variants(), n_per_variant=n, seed=seed)
    print(f"\n=== A/B price-objection experiment (baseline={report.baseline}, n={n}) ===")
    print(f"  {'variant':14} {'rate':>7} {'lift':>8} {'p-value':>11}  significant")
    for r in report.results:
        print(
            f"  {r.name:14} {r.rate:7.3f} {r.lift_vs_baseline:+8.3f} "
            f"{r.p_value:11.2e}  {r.significant}"
        )
    best = report.best()
    print(f"\n  Best variant: {best.name} (+{best.lift_vs_baseline:.3f} vs baseline)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SalesFlow evaluation harness")
    parser.add_argument("command", choices=["suite", "ab", "all"], nargs="?", default="all")
    parser.add_argument("--transcripts", type=Path, default=None, help="dir to write transcripts")
    parser.add_argument("--n", type=int, default=300, help="A/B calls per variant")
    parser.add_argument("--seed", type=int, default=7, help="A/B random seed")
    args = parser.parse_args(argv)

    if args.command in ("suite", "all"):
        _run_suite(args.transcripts)
    if args.command in ("ab", "all"):
        _run_ab(args.n, args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
