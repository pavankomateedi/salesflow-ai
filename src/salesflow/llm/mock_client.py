"""Deterministic, offline mock LLM.

Returns stable, content-free acknowledgements so the harness and tests run with
no network and no API key. It deliberately never emits factual policy/pricing
claims, so a grounding judge run against mock output never sees a hallucination.
"""

from __future__ import annotations

from salesflow.llm.base import LLMResponse, Message


class MockLLMClient:
    name = "mock"

    def complete(
        self,
        *,
        system: str,
        messages: list[Message],
        max_tokens: int = 512,
        temperature: float = 0.2,
        cache_system: bool = True,
    ) -> LLMResponse:
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"),
            "",
        )
        # Deterministic, neutral acknowledgement; no invented facts.
        text = "Thanks for sharing that — let me make sure I understand."
        if last_user:
            text = "Got it. " + text
        return LLMResponse(text=text, confidence=1.0, metadata={"backend": "mock"})
