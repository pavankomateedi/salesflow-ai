"""Deterministic per-turn signal analysis.

Sentiment scoring and intent cues are lexicon-based so they are exact-match
testable offline. A richer LLM scorer can replace these behind the same
functions without touching the decisioning engine.
"""

from __future__ import annotations

import re

from salesflow.domain.models import Sentiment

_WORD_RE = re.compile(r"[a-z']+")

_NEGATIVE = frozenset(
    "no not never angry frustrated ridiculous waste stop annoyed terrible awful "
    "hate worst unacceptable scam rip-off overpriced insulting".split()
)
_POSITIVE = frozenset(
    "yes yeah sure great perfect sounds good love interested awesome definitely "
    "absolutely please thanks helpful excited ready".split()
)

# Explicit "get me a human" requests.
_HUMAN_REQUEST = (
    "speak to a person",
    "talk to a human",
    "talk to someone",
    "real person",
    "speak with a representative",
    "speak to a manager",
    "agent",
    "human being",
)

# Self-disqualifying signals.
_DISQUALIFY = (
    "not interested",
    "don't need",
    "do not need",
    "no kids",
    "no children",
    "wrong number",
    "already have a tutor",
    "stop calling",
    "remove me",
    "take me off",
)

_POSITIVE_INTENT = (
    "sign up",
    "sign me up",
    "let's do it",
    "lets do it",
    "sounds good",
    "how do i start",
    "how do we start",
    "get started",
    "ready to go",
)


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def score_sentiment(text: str) -> Sentiment:
    toks = set(_tokens(text))
    neg = len(toks & _NEGATIVE)
    pos = len(toks & _POSITIVE)
    if neg > pos:
        return Sentiment.NEGATIVE
    if pos > neg:
        return Sentiment.POSITIVE
    return Sentiment.NEUTRAL


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(p in low for p in phrases)


def requests_human(text: str) -> bool:
    return _contains_any(text, _HUMAN_REQUEST)


def is_disqualifying(text: str) -> bool:
    return _contains_any(text, _DISQUALIFY)


def is_positive_intent(text: str) -> bool:
    return _contains_any(text, _POSITIVE_INTENT)


def extracts_field(field_name: str, text: str) -> str | None:
    """Very small deterministic field extractor for self-play / golden tests.

    Real calls would use LLM extraction; here we keep it simple and explicit so
    the harness is reproducible. Returns a normalised value or None.
    """
    low = text.strip()
    if not low:
        return None
    return low
