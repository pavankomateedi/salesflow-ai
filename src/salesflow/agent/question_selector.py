"""Dynamic question selection with skip-when-already-known.

Required fields are collected first (in script order), then leading fields in
descending predictive-conversion order. Fields already known from prior data are
never re-asked (PRD: "skipped if already known").
"""

from __future__ import annotations

from salesflow.domain.models import Lead

# Question phrasings, keyed by field. These are the baseline playbook variant;
# the A/B runner swaps alternative phrasings in here.
QUESTIONS: dict[str, str] = {
    "student_name": "Who would the tutoring be for — what's the student's name?",
    "grade_level": "And what grade are they in right now?",
    "subjects": "Which subjects are giving them the most trouble?",
    "performance_level": "How are they doing in that subject lately — roughly what grades?",
    "parent_contact": "What's the best email or number to reach you at?",
    "urgency": "Is there a timeline you're working toward, like an upcoming test?",
    "prior_tutoring": "Have they worked with a tutor before?",
    "test_deadline": "Is there a specific test or deadline coming up?",
    "schedule_windows": "What days or times usually work best for sessions?",
    "decision_maker": "Will anyone else be part of this decision?",
    "budget_signal": "Have you set aside a rough budget for tutoring?",
}


def next_field(lead: Lead, asked: list[str] | None = None) -> str | None:
    """Return the next field to ask about, or None if discovery is complete.

    Skips fields already known or already asked this call. Required fields take
    priority over leading fields.
    """
    asked = asked or []
    for fname in lead.missing_required():
        if fname not in asked:
            return fname
    for fname in lead.missing_leading():
        if fname not in asked:
            return fname
    return None


def question_for(field_name: str) -> str:
    return QUESTIONS.get(field_name, f"Could you tell me about {field_name}?")
