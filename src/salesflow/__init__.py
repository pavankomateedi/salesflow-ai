"""SalesFlow AI — autonomous voice sales agent.

The package is organised eval-first: the decisioning core (state machine,
question selector, escalation classifier, pivot logic, RAG retrieval) is fully
deterministic and testable offline. The LLM only handles natural-language
surfaces (utterance phrasing, sentiment, the post-call judge) behind the
``llm.LLMClient`` protocol, so the entire harness runs with a deterministic mock
when no API key is present.
"""

AGENT_VERSION = "vani-v1.0.0"
"""Per-call version tag stamped onto every transcript and decision log."""

__all__ = ["AGENT_VERSION"]
