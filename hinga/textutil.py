"""Shared text helpers: tokens, a small theme lexicon, excerpts, mood words."""

from __future__ import annotations

import re
from datetime import datetime

MOOD_LABELS = {1: "heavy", 2: "low", 3: "steady", 4: "light", 5: "bright"}

# Canonical theme -> words that count as that theme. Used by the local embedder
# and by the offline reflection. This is a lexicon, not a model of emotion.
THEMES: dict[str, tuple[str, ...]] = {
    "sleep": ("sleep", "slept", "asleep", "awake", "insomnia", "tired", "restless", "rest"),
    "commute": ("train", "commute", "station", "stalled"),
    "desk": ("desk", "meeting", "deadline", "email", "work"),
    "body": ("shoulder", "shoulders", "stretch", "walk", "walking", "walked", "breath", "breaths"),
    "food": ("lunch", "dinner", "ate", "coffee", "hungry"),
    "people": ("friend", "sister", "mom", "partner", "baby", "sam"),
    "outside": ("outside", "park", "air", "shade"),
}

_STOP = {
    "the", "and", "was", "were", "for", "with", "that", "this", "from", "have",
    "has", "had", "but", "not", "you", "your", "just", "again", "until", "then",
    "out", "off", "too", "very", "into", "about", "after", "before", "because",
    "while", "they", "them", "she", "her", "his", "him", "our", "are", "been",
    "being", "got", "kept", "through", "enough", "again",
}

_TOKEN = re.compile(r"[a-z']+")

PROMPTS = {
    "sleep": "What was happening in the hour before you tried to sleep?",
    "desk": "Where could tomorrow's lunch happen that is not the desk?",
    "commute": "Which part of the trip was yours, and which part was just the delay?",
    "body": "Where in your body did the day land, and where did it leave?",
    "people": "Who was actually there, and who were you only thinking about?",
    "food": "What did you eat, and were you at a table or still working?",
    "outside": "What did you notice outside that was not on your list?",
    "default": "What is one concrete thing from today you could still describe to a friend?",
}


def tokenize(text: str) -> list[str]:
    tokens = []
    for token in _TOKEN.findall(text.lower()):
        if len(token) < 3 or token in _STOP:
            continue
        tokens.append(token)
    return tokens


def detect_themes(text: str) -> list[str]:
    tokens = set(tokenize(text))
    found = []
    for theme, words in THEMES.items():
        if theme in tokens or any(word in tokens for word in words):
            found.append(theme)
    return found[:4]


def expand_themes(text: str) -> str:
    """Append canonical theme names so 'awake' and 'sleep' share a token."""
    themes = detect_themes(text)
    if not themes:
        return text
    return f"{text} {' '.join(themes)}"


def excerpt(text: str, limit: int = 180) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    cut = compact[:limit].rsplit(" ", 1)[0]
    return cut + "…"


def first_sentence(text: str) -> str:
    compact = " ".join(text.split())
    sentence = re.split(r"(?<=[.!?])\s+", compact, maxsplit=1)[0]
    if len(sentence) > 280:
        return excerpt(sentence, 280)
    return sentence


def date_label(moment: datetime) -> str:
    return moment.strftime("%-d %b")


def mood_label(mood: int) -> str:
    return MOOD_LABELS[mood]


_ANALYSIS_MAP = {"desk": "work", "commute": "work"}
_HOME_WORDS = {"crib", "kitchen", "apartment", "cooked"}
_FOCUS_WORDS = {"review", "focus"}


def analysis_themes(text: str) -> list[str]:
    """Map the retrieval lexicon onto the fixed analysis list. Order is stable."""
    found: list[str] = []
    for theme in detect_themes(text):
        name = _ANALYSIS_MAP.get(theme, theme)
        if name not in found:
            found.append(name)
    tokens = set(tokenize(text))
    if tokens & _HOME_WORDS and "home" not in found:
        found.append("home")
    if tokens & _FOCUS_WORDS and "focus" not in found:
        found.append("focus")
    allowed = {"sleep", "body", "work", "people", "food", "outside", "home", "focus"}
    return [name for name in found if name in allowed][:4]
