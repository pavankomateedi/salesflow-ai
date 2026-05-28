"""LLM client protocol and shared request/response types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class Message:
    """A single chat message."""

    role: str  # "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    """A completion plus a confidence signal used by the escalation classifier."""

    text: str
    confidence: float = 1.0
    metadata: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class LLMClient(Protocol):
    """Minimal completion interface.

    Implementations must be safe to call without network access only in the
    mock case; the live Claude backend obviously requires a key. ``cache_system``
    signals that the (large, stable) system prompt should be prompt-cached.
    """

    name: str

    def complete(
        self,
        *,
        system: str,
        messages: list[Message],
        max_tokens: int = 512,
        temperature: float = 0.2,
        cache_system: bool = True,
    ) -> LLMResponse: ...
