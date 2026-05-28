"""Live Deepgram Nova-3 streaming STT adapter (requires DEEPGRAM_API_KEY).

Stub implementing the :class:`STT` protocol. The mock backend is used for all
offline tests; this is wired up when going live. Kept import-safe so the package
loads without the optional ``deepgram-sdk`` dependency.
"""

from __future__ import annotations

import os

from salesflow.voice.interfaces import AudioChunk, Transcript


class DeepgramSTT:
    latency_ms = 150  # Nova-3 streaming target

    def __init__(self, model: str = "nova-3") -> None:
        if not os.environ.get("DEEPGRAM_API_KEY"):
            raise RuntimeError("DEEPGRAM_API_KEY is not set")
        self.model = model
        # Real impl: open a streaming websocket to Deepgram here.

    def transcribe(self, audio: AudioChunk) -> Transcript:  # pragma: no cover - live only
        raise NotImplementedError("Wire up the Deepgram streaming client for live calls.")
