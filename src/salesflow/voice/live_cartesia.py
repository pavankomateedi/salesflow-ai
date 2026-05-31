"""Live Cartesia Sonic TTS adapter (requires CARTESIA_API_KEY).

Implements the :class:`TTS` protocol by streaming raw PCM from Cartesia's Sonic
model. Kept import-safe without the optional ``cartesia`` dependency so the
offline mock remains the default and the test suite never needs the SDK or a key.

The synthesize body runs only with a real key, so it is excluded from coverage;
its contract (returns an ``AudioChunk`` whose ``pcm`` is 16-bit mono PCM at
``sample_rate``) is what the WebSocket voice loop and the browser player rely on.
"""

from __future__ import annotations

import os
from typing import Any

from salesflow.voice.interfaces import AudioChunk

DEFAULT_MODEL = "sonic-2"
# Default voice: an energetic female American English voice ("Brooke" / similar)
# so Vani (a female persona) sounds engaged and upbeat rather than flat. Override
# per-deployment with the ``CARTESIA_VOICE_ID`` env var; browse alternatives at
# https://play.cartesia.ai/voices and copy the voice id from any voice card.
DEFAULT_VOICE_ID = "6f84f4b8-58a2-430c-8c79-688dad597532"
# Speech speed: Cartesia's ModelSpeed is "slow" | "normal" | "fast". "fast"
# reads as more energetic; override with ``CARTESIA_VOICE_SPEED``.
DEFAULT_SPEED = "fast"
DEFAULT_SAMPLE_RATE = 16000


class CartesiaTTS:
    latency_ms = 100  # Sonic time-to-first-audio target

    def __init__(
        self,
        voice_id: str | None = None,
        model: str = DEFAULT_MODEL,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
    ) -> None:
        if not os.environ.get("CARTESIA_API_KEY"):
            raise RuntimeError("CARTESIA_API_KEY is not set")
        try:
            from cartesia import Cartesia
        except ImportError as exc:  # pragma: no cover - optional extra
            raise RuntimeError("cartesia SDK not installed (pip install salesflow[voice])") from exc

        self._client = Cartesia(api_key=os.environ["CARTESIA_API_KEY"])
        self.voice_id = voice_id or os.environ.get("CARTESIA_VOICE_ID", DEFAULT_VOICE_ID)
        self.model = model
        self.sample_rate = sample_rate
        self.speed: Any = os.environ.get("CARTESIA_VOICE_SPEED", DEFAULT_SPEED)

    def synthesize(self, text: str) -> AudioChunk:  # pragma: no cover - live only
        # The SDK's output_format is a strict TypedDict union; the raw dict shape
        # works at runtime but mypy can't disambiguate without an explicit cast.
        output_format: Any = {
            "container": "raw",
            "encoding": "pcm_s16le",
            "sample_rate": self.sample_rate,
        }
        voice: Any = {"mode": "id", "id": self.voice_id}
        chunks = self._client.tts.bytes(
            model_id=self.model,
            transcript=text,
            voice=voice,
            language="en",
            output_format=output_format,
            speed=self.speed,
        )
        pcm = b"".join(chunks)
        # ~150 wpm => ~400ms/word is too slow; estimate ~60ms/word for metrics.
        duration_ms = max(1, len(text.split())) * 60
        return AudioChunk(duration_ms=duration_ms, text=text, pcm=pcm)
