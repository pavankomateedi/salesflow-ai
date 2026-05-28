"""Evaluation: self-play harness, KPI scorers, grounding judge, golden set."""

from salesflow.eval.harness import run_call, run_suite
from salesflow.eval.judge import GroundingJudge, JudgeVerdict
from salesflow.eval.scorers import KPIReport, score_calls

__all__ = [
    "GroundingJudge",
    "JudgeVerdict",
    "KPIReport",
    "run_call",
    "run_suite",
    "score_calls",
]
