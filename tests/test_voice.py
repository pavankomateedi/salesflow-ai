from __future__ import annotations

import os

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


def test_live_adapters_require_keys() -> None:
    from salesflow.voice.live_cartesia import CartesiaTTS
    from salesflow.voice.live_deepgram import DeepgramSTT

    if not os.environ.get("DEEPGRAM_API_KEY"):
        with pytest.raises(RuntimeError):
            DeepgramSTT()
    if not os.environ.get("CARTESIA_API_KEY"):
        with pytest.raises(RuntimeError):
            CartesiaTTS()
