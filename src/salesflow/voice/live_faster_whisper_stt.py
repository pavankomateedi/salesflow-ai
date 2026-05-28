"""Local faster-whisper STT adapter — no API key, fully on-device.

The safest option when API-key access is unreliable: runs entirely offline.
Latency depends on hardware and model size (``tiny``/``base`` are fastest;
``small``/``medium`` are more accurate). Implements the :class:`STT` protocol;
import-safe without the optional ``faster-whisper`` package.
"""

from __future__ import annotations

from salesflow.voice.interfaces import AudioChunk, Transcript

_SAMPLE_RATE = 16_000


class LocalWhisperSTT:
    latency_ms = 300  # hardware-dependent; reserve a conservative budget

    def __init__(
        self, model_size: str = "base", device: str = "auto", compute_type: str = "int8"
    ) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - optional extra
            raise RuntimeError(
                "faster-whisper not installed (pip install salesflow[voice])"
            ) from exc

        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, audio: AudioChunk) -> Transcript:  # pragma: no cover - live only
        import numpy as np

        # 16-bit PCM -> float32 in [-1, 1], as faster-whisper expects.
        samples = np.frombuffer(audio.pcm, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _info = self._model.transcribe(samples, language="en", beam_size=1)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return Transcript(text=text, confidence=1.0, is_final=True)
