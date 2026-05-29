"""STT provider selection.

Picks a speech-to-text backend by name (or the ``SALESFLOW_STT`` env var),
returning the deterministic mock when nothing is configured so the pipeline and
tests still run offline. Live providers are imported lazily so their optional
SDKs are only required when actually selected.

Providers:
  - ``mock``    : deterministic offline backend (default)
  - ``cartesia``: Cartesia Ink-Whisper streaming STT (reuses the Cartesia key)
  - ``groq``    : Groq whisper-large-v3-turbo
  - ``local``   : faster-whisper, fully on-device, no API key
"""

from __future__ import annotations

import os

from salesflow.voice.interfaces import STT, TTS
from salesflow.voice.mock import MockSTT, MockTTS

_ALIASES = {"faster-whisper": "local", "faster_whisper": "local", "whisper": "local"}


def voice_available() -> bool:
    """True when a live voice backend (Cartesia) is usable (key present)."""
    return bool(os.environ.get("CARTESIA_API_KEY"))


def get_tts(provider: str | None = None) -> TTS:
    """Return a TTS backend. ``auto`` uses Cartesia when a key is set, else mock."""
    name = (provider or os.environ.get("SALESFLOW_TTS", "auto")).strip().lower()
    if name == "cartesia" or (name == "auto" and voice_available()):
        from salesflow.voice.live_cartesia import CartesiaTTS

        return CartesiaTTS()
    return MockTTS()


def get_stt(provider: str | None = None) -> STT:
    name = (provider or os.environ.get("SALESFLOW_STT", "mock")).strip().lower()
    name = _ALIASES.get(name, name)

    if name in ("", "mock"):
        return MockSTT()
    if name == "cartesia":
        from salesflow.voice.live_cartesia_stt import CartesiaSTT

        return CartesiaSTT()
    if name == "groq":
        from salesflow.voice.live_groq_stt import GroqSTT

        return GroqSTT()
    if name == "local":
        from salesflow.voice.live_faster_whisper_stt import LocalWhisperSTT

        return LocalWhisperSTT()
    raise ValueError(
        f"Unknown STT provider {name!r}. Use one of: mock, cartesia, groq, local."
    )
