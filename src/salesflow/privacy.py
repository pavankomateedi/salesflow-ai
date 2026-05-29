"""PII scrubbing for the stored transcript database.

The PRD calls for a *PII-protected* transcript database. Transcripts are
therefore persisted with personal data masked: email addresses, phone numbers,
and any known person-name values from the lead record. Masking is deterministic
(pure regex/string substitution) so observability tests can assert exact output,
and it is applied at write time so raw PII never lands on disk.
"""

from __future__ import annotations

import re

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# A run of >=8 phone-ish characters containing at least 7 digits.
_PHONE = re.compile(r"(?<![\w])\+?[\d][\d\-.\s()]{6,}\d(?![\w])")

EMAIL_MASK = "[EMAIL]"
PHONE_MASK = "[PHONE]"
NAME_MASK = "[NAME]"


def _has_enough_digits(match: re.Match[str]) -> str:
    digits = sum(ch.isdigit() for ch in match.group(0))
    return PHONE_MASK if digits >= 7 else match.group(0)


def scrub_text(text: str, names: tuple[str, ...] = ()) -> str:
    """Mask emails, phone numbers, and known name values in free text."""
    out = _EMAIL.sub(EMAIL_MASK, text)
    out = _PHONE.sub(_has_enough_digits, out)
    for name in names:
        token = name.strip()
        if len(token) >= 2:
            out = re.sub(rf"\b{re.escape(token)}\b", NAME_MASK, out, flags=re.IGNORECASE)
    return out


def scrub_phone(phone: str) -> str:
    """Mask a phone identifier, keeping only the last 2 digits for support refs."""
    digits = [c for c in phone if c.isdigit()]
    if len(digits) < 2:
        return PHONE_MASK
    return f"{PHONE_MASK}··{''.join(digits[-2:])}"
