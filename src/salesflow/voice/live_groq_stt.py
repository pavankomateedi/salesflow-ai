"""Groq Whisper-large-v3-turbo STT adapter (requires GROQ_API_KEY).

Fast, cheap fallback if Cartesia STT isn't on your plan. Easy free key signup.
Note: Groq's Whisper is chunk-based (very low per-chunk latency, ~200ms) rather
than true websocket streaming — feed it short buffered chunks. Implements the
:class:`STT` protocol; import-safe without the optional ``groq`` SDK.
"""

from __future__ import annotations

import io
import os

from salesflow.voice.interfaces import AudioChunk, Transcript


class GroqSTT:
    latency_ms = 200  # per-chunk transcription target

    def __init__(self, model: str = "whisper-large-v3-turbo") -> None:
        if not os.environ.get("GROQ_API_KEY"):
            raise RuntimeError("GROQ_API_KEY is not set")
        try:
            from groq import Groq
        except ImportError as exc:  # pragma: no cover - optional extra
            raise RuntimeError("groq SDK not installed (pip install salesflow[voice])") from exc

        self._client = Groq()
        self.model = model

    def transcribe(self, audio: AudioChunk) -> Transcript:  # pragma: no cover - live only
        buf = io.BytesIO(audio.pcm)
        buf.name = "chunk.wav"
        resp = self._client.audio.transcriptions.create(
            file=buf,
            model=self.model,
            response_format="json",
        )
        return Transcript(text=resp.text, confidence=1.0, is_final=True)
