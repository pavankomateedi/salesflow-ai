"""Cartesia Ink-Whisper streaming STT adapter (requires CARTESIA_API_KEY).

The Deepgram replacement and default live STT: it reuses the same Cartesia key as
the TTS adapter, so one provider/key covers both ends of the voice pipeline.
Ink-Whisper is built on whisper-large-v3-turbo with dynamic chunking for
conversational low latency. Implements the :class:`STT` protocol; kept
import-safe without the optional ``cartesia`` SDK.
"""

from __future__ import annotations

import os

from salesflow.voice.interfaces import AudioChunk, Transcript

# Cartesia API version pin (see docs.cartesia.ai). Bump deliberately.
CARTESIA_VERSION = "2026-03-01"


class CartesiaSTT:
    latency_ms = 150  # Ink-Whisper conversational target

    def __init__(self, model: str = "ink-whisper", language: str = "en") -> None:
        if not os.environ.get("CARTESIA_API_KEY"):
            raise RuntimeError("CARTESIA_API_KEY is not set")
        try:
            from cartesia import Cartesia
        except ImportError as exc:  # pragma: no cover - optional extra
            raise RuntimeError("cartesia SDK not installed (pip install salesflow[voice])") from exc

        self._client = Cartesia(api_key=os.environ["CARTESIA_API_KEY"])
        self.model = model
        self.language = language

    def transcribe(self, audio: AudioChunk) -> Transcript:  # pragma: no cover - live only
        # Streaming usage opens a websocket session and feeds PCM chunks; for a
        # single buffered chunk we use the batch endpoint and take the final text.
        result = self._client.stt.transcribe(
            model=self.model,
            language=self.language,
            audio=audio.pcm,
        )
        return Transcript(text=result.text, confidence=1.0, is_final=True)
