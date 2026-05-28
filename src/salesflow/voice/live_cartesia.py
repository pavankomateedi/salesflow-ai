"""Live Cartesia Sonic 3 TTS adapter (requires CARTESIA_API_KEY).

Stub implementing the :class:`TTS` protocol; the mock backend covers offline
tests. Kept import-safe without the optional ``cartesia`` dependency.
"""

from __future__ import annotations

import os

from salesflow.voice.interfaces import AudioChunk


class CartesiaTTS:
    latency_ms = 100  # Sonic 3 time-to-first-audio target

    def __init__(self, voice: str = "alex-neutral") -> None:
        if not os.environ.get("CARTESIA_API_KEY"):
            raise RuntimeError("CARTESIA_API_KEY is not set")
        self.voice = voice
        # Real impl: open a streaming TTS session to Cartesia here.

    def synthesize(self, text: str) -> AudioChunk:  # pragma: no cover - live only
        raise NotImplementedError("Wire up the Cartesia streaming client for live calls.")
