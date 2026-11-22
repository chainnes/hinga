"""Phrase-list backstop. It runs before any model call and it does not assess a person."""

from __future__ import annotations

import re

from hinga.copy import DISCLAIMER, FIXED_SAFETY_RESPONSE, RESOURCES, SAFETY_TITLE
from hinga.schemas import Resource, SafetyHold

# Word-boundary phrases only. Ordinary stress ("this deadline is killing me")
# must not match. Graphic detail is intentionally not listed.
_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bkill myself\b",
        r"\bkilling myself\b",
        r"\bwant to die\b",
        r"\bwanted to die\b",
        r"\bwish i (?:was|were) dead\b",
        r"\bend my life\b",
        r"\bending my life\b",
        r"\bsuicid(?:e|al)\b",
        r"\bhurt myself\b",
        r"\bhurting myself\b",
        r"\bself[\s-]?harm\b",
        r"\b(?:do not|don't|dont) want to (?:live|be alive)\b",
        r"\bno reason to live\b",
        r"\bbetter off dead\b",
    )
)

# The hard-gate list. Every one of these must hit the fixed response.
CRISIS_PHRASES: tuple[str, ...] = (
    "I want to die",
    "I wanted to die last night",
    "I wish I was dead",
    "I wish I were dead",
    "I am going to kill myself",
    "killing myself is all I think about",
    "I want to end my life",
    "I keep thinking about ending my life",
    "I keep thinking about suicide",
    "I feel suicidal",
    "I want to hurt myself",
    "I keep hurting myself",
    "this is self-harm",
    "this is self harm",
    "I don't want to live",
    "I dont want to live",
    "I do not want to be alive",
    "I have no reason to live",
    "I would be better off dead",
    "They would be better off dead if I kill myself",
)

PREVIEW_PHRASE = CRISIS_PHRASES[0]


def is_crisis(text: str) -> bool:
    if not text or not text.strip():
        return False
    return any(pattern.search(text) for pattern in _PATTERNS)


def safety_payload(*, stored: bool) -> SafetyHold:
    """The same sentences every time. `stored` is the only field that varies."""
    return SafetyHold(
        stored=stored,
        title=SAFETY_TITLE,
        message=FIXED_SAFETY_RESPONSE,
        resources=[Resource.model_validate(item) for item in RESOURCES],
        disclaimer=DISCLAIMER,
    )
