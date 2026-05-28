"""Grounded retrieval over the policy / objection / competitive corpus.

Retrieval is deterministic keyword-overlap scoring (no embedding service needed
for the offline core; a vector backend is a drop-in behind the same interface).
The point that matters for correctness: policy answers are *retrieval-only* and
the objection rebuttals are parsed from the version-controlled playbook, never
generated at runtime.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "data"
_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "the a an and or of to in is are for on with my our your you i we it this that "
    "do does can could would will be have has how what when where about me us".split()
)


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS}


@dataclass(frozen=True)
class KBChunk:
    """A retrievable section, tagged with its source document and heading."""

    source: str  # e.g. "policy"
    title: str  # the "## heading"
    body: str
    keywords: frozenset[str]

    def score(self, query_tokens: set[str]) -> int:
        return len(self.keywords & query_tokens)


class ObjectionType(StrEnum):
    PRICE = "price"
    COMPETITOR = "competitor"
    TIMING = "timing"
    DECISION_MAKER = "decision_maker"
    EFFECTIVENESS = "effectiveness"


# Maps an objection type to its section heading in objections.md.
_OBJECTION_SECTION = {
    ObjectionType.PRICE: "Price / Too Expensive",
    ObjectionType.COMPETITOR: "Competitor / Already Looking Elsewhere",
    ObjectionType.TIMING: "Timing / Not Right Now",
    ObjectionType.DECISION_MAKER: "Need to Talk to Spouse / Decision Maker",
    ObjectionType.EFFECTIVENESS: "Effectiveness / Will This Actually Work",
}

# Phrase markers for classifying free-text prospect objections. Phrase-based
# (substring) matching avoids false positives on neutral field answers that
# merely happen to contain a single shared word (e.g. "time", "test").
_OBJECTION_MARKERS: dict[ObjectionType, tuple[str, ...]] = {
    # Note: a bare pricing *question* ("how much does it cost?") is NOT an
    # objection — it is answered from the grounded pricing config. Markers here
    # are price *complaints* only.
    ObjectionType.PRICE: (
        "expensive", "afford", "too much", "cost too", "pricey", "out of budget",
        "cheaper", "that's a lot", "thats a lot",
    ),
    ObjectionType.COMPETITOR: (
        "looking at", "another company", "competitor", "compare to", "wyzant",
        "varsity tutors", "someone else", "other options", "shopping around",
    ),
    ObjectionType.TIMING: (
        "not right now", "maybe later", "not a good time", "too busy",
        "circle back", "down the road", "after the holidays", "next year",
    ),
    ObjectionType.DECISION_MAKER: (
        "talk to my", "ask my", "my husband", "my wife", "my spouse",
        "my partner", "discuss with", "run it by", "check with my",
    ),
    ObjectionType.EFFECTIVENESS: (
        "does it work", "will it work", "actually help", "guarantee",
        "really help", "prove", "not sure it", "how do i know",
    ),
}


def classify_objection(text: str) -> ObjectionType | None:
    """Deterministic objection classification from prospect text.

    Returns the objection type whose phrase markers best match, or None when no
    marker is present (so plain field answers are not misread as objections).
    """
    low = text.lower()
    best: tuple[int, ObjectionType] | None = None
    for otype, markers in _OBJECTION_MARKERS.items():
        hits = sum(1 for m in markers if m in low)
        if hits and (best is None or hits > best[0]):
            best = (hits, otype)
    return best[1] if best else None


@dataclass(frozen=True)
class ARCRebuttal:
    """A parsed Acknowledge / Respond / Close rebuttal from the playbook."""

    objection: ObjectionType
    acknowledge: str
    respond: str
    close: str
    source: str = "objections"

    def render(self) -> str:
        return f"{self.acknowledge} {self.respond} {self.close}"


def _parse_sections(text: str) -> dict[str, str]:
    """Split a markdown doc into {heading: body} by level-2 (`## `) headings."""
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = line[3:].strip()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


class KnowledgeBase:
    """Loads the corpus and serves grounded retrieval + objection rebuttals."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self._dir = data_dir or _DATA_DIR
        self.chunks: list[KBChunk] = []
        self._rebuttals: dict[ObjectionType, ARCRebuttal] = {}
        self._load()

    def _load(self) -> None:
        for path in sorted(self._dir.glob("*.md")):
            source = path.stem
            sections = _parse_sections(path.read_text(encoding="utf-8"))
            # The objection playbook is internal rebuttal content served via
            # rebuttal(); it must NOT pollute the customer-facing policy/
            # competitive retrieval corpus.
            if source == "objections":
                self._parse_rebuttals(sections)
                continue
            for title, body in sections.items():
                self.chunks.append(
                    KBChunk(
                        source=source,
                        title=title,
                        body=body,
                        keywords=frozenset(_tokens(title + " " + body)),
                    )
                )

    def _parse_rebuttals(self, sections: dict[str, str]) -> None:
        for otype, heading in _OBJECTION_SECTION.items():
            body = sections.get(heading)
            if not body:
                continue
            parts = {"acknowledge": "", "respond": "", "close": ""}
            for line in body.splitlines():
                for key in parts:
                    prefix = key.capitalize() + ":"
                    if line.startswith(prefix):
                        parts[key] = line[len(prefix):].strip()
            self._rebuttals[otype] = ARCRebuttal(objection=otype, **parts)

    def retrieve(self, query: str, k: int = 3) -> list[KBChunk]:
        """Return the top-``k`` chunks by keyword overlap (score > 0 only)."""
        qt = _tokens(query)
        scored = [(c.score(qt), c) for c in self.chunks]
        scored = [(s, c) for s, c in scored if s > 0]
        scored.sort(key=lambda sc: (-sc[0], sc[1].source, sc[1].title))
        return [c for _, c in scored[:k]]

    def rebuttal(self, objection: ObjectionType) -> ARCRebuttal | None:
        return self._rebuttals.get(objection)
