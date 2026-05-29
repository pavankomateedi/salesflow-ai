"""LLM abstraction layer.

The decisioning core is deterministic and needs no LLM. The LLM is an optional
enhancement for natural-language surfaces (rich phrasing, LLM-driven personas,
the post-call judge). ``get_client`` returns the real OpenAI backend when an API
key is present and the deterministic mock otherwise, so the harness and the full
test suite run offline at zero cost.
"""

from __future__ import annotations

import os

from salesflow.llm.base import LLMClient, LLMResponse, Message
from salesflow.llm.mock_client import MockLLMClient


def get_client(prefer_live: bool | None = None) -> LLMClient:
    """Return an LLM client.

    Resolves to the OpenAI (GPT) backend when ``OPENAI_API_KEY`` is set (and the
    ``openai`` package is importable); otherwise the deterministic mock. Pass
    ``prefer_live=False`` to force the mock even when a key exists.
    """
    if prefer_live is False:
        return MockLLMClient()
    has_key = bool(os.environ.get("OPENAI_API_KEY"))
    if prefer_live or has_key:
        try:
            from salesflow.llm.openai_client import OpenAIClient

            return OpenAIClient()
        except Exception:  # fall back to mock if SDK/key unusable
            if prefer_live:
                raise
            return MockLLMClient()
    return MockLLMClient()


__all__ = ["LLMClient", "LLMResponse", "Message", "MockLLMClient", "get_client"]
