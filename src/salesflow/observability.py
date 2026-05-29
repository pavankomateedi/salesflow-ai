"""Per-call transcript + decision log serialisation, with version tagging.

Every call log carries the ``agent_version`` so KPIs can be attributed per
variant (the foundation of the A/B improvement loop). When ``redact=True`` the
serialised record is PII-protected: phone, email, and known name values are
masked (see :mod:`salesflow.privacy`). ``save_transcript`` redacts by default so
the on-disk transcript database never stores raw personal data.
"""

from __future__ import annotations

import json
from pathlib import Path

from salesflow.domain.models import CallLog
from salesflow.privacy import scrub_phone, scrub_text


def to_dict(call: CallLog, *, redact: bool = False) -> dict[str, object]:
    names: tuple[str, ...] = ()
    if redact:
        student = call.collected_fields.get("student_name")
        names = (student,) if student else ()

    def field(value: str) -> str:
        return scrub_text(value, names) if redact else value

    return {
        "session_id": call.session_id,
        "phone": scrub_phone(call.phone) if redact else call.phone,
        "agent_version": call.agent_version,
        "outcome": call.outcome.value,
        "final_phase": call.final_phase.value,
        "escalation_trigger": (
            call.escalation_trigger.value if call.escalation_trigger else None
        ),
        "redacted": redact,
        "collected_fields": {k: field(v) for k, v in call.collected_fields.items()},
        "turns": [
            {
                "speaker": t.speaker,
                "text": field(t.text),
                "phase": t.phase.value,
                "sentiment": t.sentiment.value,
                "decision": t.decision,
            }
            for t in call.turns
        ],
    }


def save_transcript(call: CallLog, directory: Path, *, redact: bool = True) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{call.session_id}.json"
    path.write_text(json.dumps(to_dict(call, redact=redact), indent=2), encoding="utf-8")
    return path
