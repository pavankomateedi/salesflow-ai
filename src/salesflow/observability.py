"""Per-call transcript + decision log serialisation, with version tagging.

Every call log carries the ``agent_version`` so KPIs can be attributed per
variant (the foundation of the A/B improvement loop).
"""

from __future__ import annotations

import json
from pathlib import Path

from salesflow.domain.models import CallLog


def to_dict(call: CallLog) -> dict[str, object]:
    return {
        "session_id": call.session_id,
        "phone": call.phone,
        "agent_version": call.agent_version,
        "outcome": call.outcome.value,
        "final_phase": call.final_phase.value,
        "escalation_trigger": (
            call.escalation_trigger.value if call.escalation_trigger else None
        ),
        "collected_fields": call.collected_fields,
        "turns": [
            {
                "speaker": t.speaker,
                "text": t.text,
                "phase": t.phase.value,
                "sentiment": t.sentiment.value,
                "decision": t.decision,
            }
            for t in call.turns
        ],
    }


def save_transcript(call: CallLog, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{call.session_id}.json"
    path.write_text(json.dumps(to_dict(call), indent=2), encoding="utf-8")
    return path
