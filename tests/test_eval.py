from __future__ import annotations

import json

from salesflow.domain.models import (
    CallLog,
    Outcome,
    Phase,
    Sentiment,
    Turn,
)
from salesflow.eval.harness import run_suite
from salesflow.eval.judge import GroundingJudge
from salesflow.eval.scorers import score_calls
from salesflow.observability import save_transcript, to_dict
from salesflow.personas import ALL_PERSONAS


def test_suite_runs_every_persona_to_a_terminal_state() -> None:
    logs = run_suite()
    assert len(logs) == len(ALL_PERSONAS)
    for log in logs:
        assert log.final_phase.is_terminal, log.session_id
        assert log.agent_version  # version tag stamped on every call


def _make_log(outcome: Outcome, *, price_text: str, session: str = "t") -> CallLog:
    turns = [
        Turn(speaker="agent", text=price_text, phase=Phase.QUALIFICATION),
        Turn(speaker="prospect", text="ok", phase=Phase.QUALIFICATION, sentiment=Sentiment.NEUTRAL),
    ]
    return CallLog(
        session_id=session,
        phone="+1",
        agent_version="test-v1",
        turns=turns,
        outcome=outcome,
        final_phase=Phase.CLOSE,
        escalation_trigger=None,
        collected_fields={},
    )


def test_judge_passes_grounded_pricing_and_flags_invented_pricing() -> None:
    judge = GroundingJudge()
    grounded = _make_log(Outcome.CLOSED_WON, price_text="Standard is $60/hour.")
    invented = _make_log(Outcome.CLOSED_WON, price_text="I can do $25/hour just for you.")
    assert judge.judge(grounded).grounded is True
    bad = judge.judge(invented)
    assert bad.grounded is False
    assert bad.flags[0]["issue"] == "ungrounded_price"
    assert judge.hallucination_rate([grounded, invented]) == 0.5


def test_real_self_play_has_no_hallucinations() -> None:
    logs = run_suite()
    assert GroundingJudge().hallucination_rate(logs) == 0.0


def test_scorers_compute_expected_kpis() -> None:
    report = score_calls(run_suite())
    assert report.n_calls == 5
    # 2 of 5 personas convert (Rita, Henry).
    assert report.conversion_rate == 0.4
    assert report.escalation_rate == 0.4  # Paula + Sam
    assert report.discovery_completion_rate == 1.0
    assert report.false_positive_close_rate == 0.0


def test_transcript_serialises_round_trip(tmp_path) -> None:
    log = run_suite()[0]
    path = save_transcript(log, tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["agent_version"] == log.agent_version
    assert data["turns"]
    assert data["redacted"] is True  # stored transcript DB is PII-protected
    assert to_dict(log)["session_id"] == log.session_id


def test_dashboard_data_assembles() -> None:
    from salesflow.eval.dashboard import build_dashboard

    d = build_dashboard(n_ab=40)
    assert d["agent_version"]
    synth = d["synthetic"]
    assert isinstance(synth, dict) and synth["kpis"]
    assert d["ab"]["variants"] and d["ab"]["best"]
    assert synth["sample_transcript"]["redacted"] is True
