from __future__ import annotations

from salesflow.domain.models import CallLog, Outcome, Phase, Turn
from salesflow.observability import to_dict
from salesflow.privacy import scrub_phone, scrub_text


def test_scrub_text_masks_email_phone_and_name() -> None:
    text = "Hi, I'm Sam, reach me at sam.parent@example.com or 555-123-4567."
    out = scrub_text(text, names=("Sam",))
    assert "[EMAIL]" in out
    assert "[PHONE]" in out
    assert "[NAME]" in out
    assert "sam.parent@example.com" not in out
    assert "555-123-4567" not in out


def test_scrub_text_does_not_overmask_short_numbers() -> None:
    # A budget figure / short number is not a phone number.
    assert scrub_text("We set aside about 200 a month.") == "We set aside about 200 a month."


def test_scrub_phone_keeps_only_last_two_digits() -> None:
    assert scrub_phone("+15550001142").endswith("42")
    assert "5550001142" not in scrub_phone("+15550001142")


def test_to_dict_redacts_pii_in_transcript() -> None:
    turns = [
        Turn(speaker="prospect", text="I'm Mia, email mia@example.com", phase=Phase.DISCOVERY),
        Turn(speaker="agent", text="Thanks Mia!", phase=Phase.DISCOVERY),
    ]
    call = CallLog(
        session_id="s1",
        phone="+15551234567",
        agent_version="vani-v1.0.0",
        turns=turns,
        outcome=Outcome.IN_PROGRESS,
        final_phase=Phase.DISCOVERY,
        escalation_trigger=None,
        collected_fields={"student_name": "Mia", "parent_contact": "mia@example.com"},
    )
    redacted = to_dict(call, redact=True)
    assert redacted["redacted"] is True
    assert redacted["phone"].startswith("[PHONE]")  # type: ignore[union-attr]
    blob = str(redacted)
    assert "mia@example.com" not in blob
    assert "Mia" not in blob
    # Raw mode is unchanged (back-compat for round-trip serialisation).
    assert to_dict(call)["phone"] == "+15551234567"
