"""Deterministic mock voice backends.

Latencies default to the PRD's per-stage budget so the offline pipeline test
asserts the same ≤800ms round-trip the live stack targets. Mock audio is just
text with a duration (~60ms per word) so barge-in timing is reproducible.
"""

from __future__ import annotations

from collections import deque

from salesflow.voice.interfaces import AudioChunk, Transcript

_MS_PER_WORD = 60


def text_to_audio(text: str) -> AudioChunk:
    words = max(1, len(text.split()))
    return AudioChunk(duration_ms=words * _MS_PER_WORD, text=text)


class MockVAD:
    def __init__(self, latency_ms: int = 50) -> None:
        self.latency_ms = latency_ms

    def is_speech(self, audio: AudioChunk) -> bool:
        return bool(audio.text.strip()) or audio.duration_ms > 0


class MockSTT:
    def __init__(self, latency_ms: int = 150) -> None:
        self.latency_ms = latency_ms

    def transcribe(self, audio: AudioChunk) -> Transcript:
        return Transcript(text=audio.text, confidence=1.0, is_final=True)


class MockTTS:
    def __init__(self, latency_ms: int = 100) -> None:
        self.latency_ms = latency_ms

    def synthesize(self, text: str) -> AudioChunk:
        return text_to_audio(text)


class MockTransport:
    """In-memory transport; pre-loaded with the prospect's audio turns."""

    def __init__(self, network_ms: int = 50) -> None:
        self.network_ms = network_ms
        self._inbound: deque[AudioChunk] = deque()
        self.sent: list[AudioChunk] = []

    def enqueue(self, text: str) -> None:
        self._inbound.append(text_to_audio(text))

    def send(self, audio: AudioChunk) -> None:
        self.sent.append(audio)

    def receive(self) -> AudioChunk | None:
        return self._inbound.popleft() if self._inbound else None
