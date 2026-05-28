"""Protocols and types for the voice pipeline.

In the offline mock, an :class:`AudioChunk` carries the underlying text plus a
duration so latency and barge-in timing can be simulated deterministically. Live
adapters carry real PCM bytes behind the identical interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class AudioChunk:
    """A unit of audio. ``text`` is the mock payload; ``pcm`` is for live use."""

    duration_ms: int
    text: str = ""
    pcm: bytes = b""


@dataclass
class Transcript:
    text: str
    confidence: float = 1.0
    is_final: bool = True


@runtime_checkable
class STT(Protocol):
    latency_ms: int

    def transcribe(self, audio: AudioChunk) -> Transcript: ...


@runtime_checkable
class TTS(Protocol):
    latency_ms: int  # time-to-first-audio

    def synthesize(self, text: str) -> AudioChunk: ...


@runtime_checkable
class VAD(Protocol):
    latency_ms: int

    def is_speech(self, audio: AudioChunk) -> bool: ...


@runtime_checkable
class Transport(Protocol):
    network_ms: int

    def send(self, audio: AudioChunk) -> None: ...

    def receive(self) -> AudioChunk | None: ...
