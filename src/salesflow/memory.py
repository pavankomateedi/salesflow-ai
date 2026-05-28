"""Cross-call persistent memory.

Keyed by session-id + phone (the "double-key", PRD decision) so a recycled phone
number can't inherit a prior caller's data. Backed by an in-memory dict with
optional JSON persistence; a Redis/Postgres backend is a drop-in behind the same
interface for production.
"""

from __future__ import annotations

import json
from pathlib import Path

from salesflow.domain.models import CallLog, Lead


class SessionStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._data: dict[str, dict[str, str]] = {}
        if path and path.exists():
            self._data = json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _key(session_id: str, phone: str) -> str:
        return f"{session_id}::{phone}"

    def known_fields(self, session_id: str, phone: str) -> dict[str, str]:
        return dict(self._data.get(self._key(session_id, phone), {}))

    def load_lead(self, session_id: str, phone: str) -> Lead:
        """Build a Lead pre-populated with whatever was learned on prior calls."""
        return Lead(phone=phone, known=self.known_fields(session_id, phone))

    def remember(self, session_id: str, fields: dict[str, str], *, phone: str) -> None:
        key = self._key(session_id, phone)
        merged = self._data.setdefault(key, {})
        merged.update({k: v for k, v in fields.items() if v})
        self._persist()

    def save_call(self, session_id: str, call: CallLog) -> None:
        """Persist fields collected during a call for carry-over next time."""
        self.remember(session_id, call.collected_fields, phone=call.phone)

    def _persist(self) -> None:
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
