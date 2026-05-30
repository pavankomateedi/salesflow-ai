"""OpenAI (GPT) backend.

OpenAI automatically prompt-caches stable prefixes (>=1024 tokens) server-side,
so the large, stable system prompt (persona + playbook + retrieved KB context)
is cached without an explicit cache-control marker — ``cache_system`` is accepted
for protocol parity but needs no action here. Raises on construction if the SDK
is missing or no key is configured, so ``get_client`` can fall back to the mock.
"""

from __future__ import annotations

import os
from typing import Any

from salesflow.llm.base import LLMResponse, Message

DEFAULT_MODEL = "gpt-4o-mini"  # voice loop needs sub-second turns; mini ~500ms


class OpenAIClient:
    """Thin wrapper over the OpenAI Chat Completions API."""

    name = "openai"

    def __init__(self, model: str | None = None) -> None:
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError("openai SDK not installed (pip install salesflow[llm])") from exc

        self._client = OpenAI()
        self.model = model or os.environ.get("SALESFLOW_MODEL", DEFAULT_MODEL)

    def complete(
        self,
        *,
        system: str,
        messages: list[Message],
        max_tokens: int = 512,
        temperature: float = 0.2,
        cache_system: bool = True,
    ) -> LLMResponse:  # pragma: no cover - live only (no key offline)
        api_messages: list[Any] = [{"role": "system", "content": system}]
        api_messages += [{"role": m.role, "content": m.content} for m in messages]

        resp = self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=api_messages,
        )
        text = resp.choices[0].message.content or ""
        metadata: dict[str, object] = {"backend": "openai", "model": self.model}
        usage = getattr(resp, "usage", None)
        if usage is not None:
            metadata["input_tokens"] = getattr(usage, "prompt_tokens", None)
            metadata["output_tokens"] = getattr(usage, "completion_tokens", None)
            details = getattr(usage, "prompt_tokens_details", None)
            if details is not None:
                metadata["cached_tokens"] = getattr(details, "cached_tokens", None)
        return LLMResponse(text=text.strip(), confidence=1.0, metadata=metadata)
