from __future__ import annotations

import os

import pytest

from salesflow.knowledge.kb import KnowledgeBase, ObjectionType
from salesflow.llm import MockLLMClient, get_client
from salesflow.llm.base import Message


def test_factory_returns_mock_when_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = get_client()
    assert client.name == "mock"


def test_force_mock_even_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    assert get_client(prefer_live=False).name == "mock"


def test_mock_is_deterministic() -> None:
    client = MockLLMClient()
    msgs = [Message(role="user", content="hello there")]
    a = client.complete(system="s", messages=msgs)
    b = client.complete(system="s", messages=msgs)
    assert a.text == b.text
    assert "$" not in a.text  # mock never invents pricing


def test_kb_parses_every_arc_rebuttal() -> None:
    kb = KnowledgeBase()
    for otype in ObjectionType:
        rebuttal = kb.rebuttal(otype)
        assert rebuttal is not None, otype
        assert rebuttal.acknowledge and rebuttal.respond and rebuttal.close
        # Rendered rebuttal is grounded prose, never a fabricated price.
        assert "$" not in rebuttal.render()


def test_live_backend_is_importable() -> None:
    # Construction must fail cleanly (not import-error) without a key.
    from salesflow.llm.openai_client import OpenAIClient

    if not os.environ.get("OPENAI_API_KEY"):
        with pytest.raises(RuntimeError):
            OpenAIClient()
