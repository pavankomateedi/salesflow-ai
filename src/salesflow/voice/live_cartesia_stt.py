"""Cartesia Ink-Whisper STT adapter (requires CARTESIA_API_KEY).

The Deepgram replacement and default live STT: reuses the same Cartesia key as
the TTS adapter, so one provider/key covers both ends of the voice pipeline.
Ink-Whisper is built on whisper-large-v3-turbo with dynamic chunking for
conversational low latency. Implements the :class:`STT` protocol; kept
import-safe without the optional ``cartesia`` SDK.

Browser audio is captured as raw PCM16 at the AudioContext sample rate (usually
48 kHz). Ink-Whisper's batch endpoint expects a complete audio file with a
header, so we wrap the PCM into a tiny in-memory WAV before sending. The SDK's
``transcribe`` parameter name changed across releases (``audio=`` in 1.x,
``file=`` in 3.x), so we try the modern call shape first and fall back.
"""

from __future__ import annotations

import io
import os
import wave
from typing import Any

from salesflow.voice.interfaces import AudioChunk, Transcript

CARTESIA_VERSION = "2026-03-01"


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap raw 16-bit mono PCM in a minimal WAV (RIFF) container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # 16-bit
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


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
        if not audio.pcm:
            return Transcript(text="", confidence=0.0, is_final=True)

        wav_bytes = _pcm_to_wav(audio.pcm, audio.sample_rate or 16000)

        # SDK 3.x exposes the file via the ``file=`` kwarg. The accepted shape is
        # either a multipart tuple or a BinaryIO; try the tuple first (most
        # SDK versions accept it), fall back to BytesIO. cast(Any) keeps mypy
        # honest about the strict typing while letting both runtime shapes work.
        attempts: tuple[Any, ...] = (
            ("audio.wav", wav_bytes, "audio/wav"),
            io.BytesIO(wav_bytes),
        )
        last_exc: Exception | None = None
        for file_arg in attempts:
            try:
                result = self._client.stt.transcribe(
                    file=file_arg,
                    model=self.model,
                    language=self.language,
                )
                text = getattr(result, "text", "") or ""
                return Transcript(text=text.strip(), confidence=1.0, is_final=True)
            except TypeError as exc:
                last_exc = exc
                continue
        raise RuntimeError(
            f"Cartesia STT file= signature mismatch: {last_exc!r}. "
            "Run `inspect.signature(client.stt.transcribe)` to find the right shape."
        )
