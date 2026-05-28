"""Real-time voice pipeline.

The pipeline (VAD -> STT -> agent -> TTS over a transport) is defined against
protocols so the deterministic mock backend exercises latency budgeting and
barge-in handling offline, while live Deepgram/Cartesia/Vapi adapters (which need
API keys) drop in behind the same interfaces.
"""

from salesflow.voice.interfaces import STT, TTS, VAD, AudioChunk, Transport
from salesflow.voice.mock import MockSTT, MockTransport, MockTTS, MockVAD
from salesflow.voice.pipeline import LATENCY_BUDGET_MS, TurnLatency, VoiceMetrics, VoicePipeline

__all__ = [
    "LATENCY_BUDGET_MS",
    "STT",
    "TTS",
    "VAD",
    "AudioChunk",
    "MockSTT",
    "MockTTS",
    "MockTransport",
    "MockVAD",
    "Transport",
    "TurnLatency",
    "VoiceMetrics",
    "VoicePipeline",
]
