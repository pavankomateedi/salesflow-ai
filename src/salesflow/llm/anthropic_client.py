"""Claude (Anthropic) backend with prompt caching.

The system prompt — agent persona, playbook, retrieved KB context — is large and
stable across turns within a call, so it is marked with ``cache_control`` to cut
latency and cost (TTFT is the dominant term in the PRD's 800ms voice budget).
"""

from __future__ import annotations

import os
from typing import Any

from salesflow.llm.base import LLMResponse, Message

DEFAULT_MODEL = "claude-sonnet-4-6"


class AnthropicClient:
    """Thin wrapper over the Anthropic Messages API.

    Raises on construction if the SDK is missing or no key is configured, so the
    ``get_client`` factory can fall back to the mock.
    """

    name = "anthropic"

    def __init__(self, model: str | None = None) -> None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError("anthropic SDK not installed (pip install salesflow[llm])") from exc

        self._client = anthropic.Anthropic()
        self.model = model or os.environ.get("SALESFLOW_MODEL", DEFAULT_MODEL)

    def complete(
        self,
        *,
        system: str,
        messages: list[Message],
        max_tokens: int = 512,
        temperature: float = 0.2,
        cache_system: bool = True,
    ) -> LLMResponse:
        # Typed as Any: the SDK's TextBlockParam / MessageParam TypedDicts are
        # stricter than the literal dicts we build, but the payload is correct.
        system_blocks: list[Any] = [{"type": "text", "text": system}]
        if cache_system:
            system_blocks[0]["cache_control"] = {"type": "ephemeral"}
        api_messages: list[Any] = [{"role": m.role, "content": m.content} for m in messages]

        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_blocks,
            messages=api_messages,
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        usage = getattr(resp, "usage", None)
        metadata: dict[str, object] = {"backend": "anthropic", "model": self.model}
        if usage is not None:
            metadata["input_tokens"] = getattr(usage, "input_tokens", None)
            metadata["output_tokens"] = getattr(usage, "output_tokens", None)
            metadata["cache_read_input_tokens"] = getattr(
                usage, "cache_read_input_tokens", None
            )
        return LLMResponse(text=text.strip(), confidence=1.0, metadata=metadata)
