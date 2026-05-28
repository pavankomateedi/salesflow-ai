from __future__ import annotations

import pytest

from salesflow.agent.agent import SalesAgent
from salesflow.domain.models import Lead, Outcome
from salesflow.personas import ReadyRita
from salesflow.voice.mock import MockSTT, MockTransport, MockTTS, MockVAD
from salesflow.voice.pipeline import LATENCY_BUDGET_MS, VoicePipeline


def _pipeline() -> VoicePipeline:
    return VoicePipeline(vad=MockVAD(), stt=MockSTT(), tts=MockTTS(), transport=MockTransport())


def test_voice_call_completes_within_latency_budget() -> None:
    pipe = _pipeline()
    log, metrics = pipe.run_call(
        SalesAgent(), ReadyRita(), Lead(phone="+15550000001"), session_id="voice-rita"
    )
    assert log.outcome == Outcome.CLOSED_WON
    assert metrics.latencies, "no turns measured"
    # Per-stage mock budget: VAD 50 + STT 150 + LLM 400 + TTS 100 + net 50 = 750ms.
    assert metrics.max_latency_ms == 50 + 150 + 400 + 100 + 50  # 750
    assert metrics.max_latency_ms <= LATENCY_BUDGET_MS
    assert metrics.within_budget
    assert metrics.p95_latency_ms <= LATENCY_BUDGET_MS


def test_barge_in_is_handled_without_audio_overlap() -> None:
    pipe = _pipeline()
    # Prospect barges in 30ms into the agent's turn-1 and turn-2 playback.
    _log, metrics = pipe.run_call(
        SalesAgent(),
        ReadyRita(),
        Lead(phone="+15550000002"),
        session_id="voice-barge",
        barge_in_turns={1: 30, 2: 30},
    )
    assert metrics.barge_ins >= 1
    assert metrics.overlaps == 0
    assert metrics.barge_in_handle_rate == 1.0


def test_stt_factory_defaults_to_mock_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    from salesflow.voice import get_stt

    monkeypatch.delenv("SALESFLOW_STT", raising=False)
    assert get_stt().name == "mock"
    assert get_stt("mock").name == "mock"


def test_stt_factory_rejects_unknown_provider() -> None:
    from salesflow.voice import get_stt

    with pytest.raises(ValueError, match="Unknown STT provider"):
        get_stt("deepgram")  # retired — must not silently resolve


def test_stt_factory_selects_provider_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from salesflow.voice import get_stt

    monkeypatch.setenv("SALESFLOW_STT", "cartesia")
    monkeypatch.delenv("CARTESIA_API_KEY", raising=False)
    # Provider chosen, but no key -> the adapter raises (proving selection works).
    with pytest.raises(RuntimeError):
        get_stt()


def test_live_stt_adapters_require_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    from salesflow.voice.live_cartesia import CartesiaTTS
    from salesflow.voice.live_cartesia_stt import CartesiaSTT
    from salesflow.voice.live_groq_stt import GroqSTT

    monkeypatch.delenv("CARTESIA_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        CartesiaSTT()
    with pytest.raises(RuntimeError):
        GroqSTT()
    with pytest.raises(RuntimeError):
        CartesiaTTS()
