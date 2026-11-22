"""Reflection and habit-insight agents.

Both return schema-validated objects. Live mode may write the sentences.
Mood labels, excerpts, habit counts, and the disclaimer are filled by code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from hinga.config import Settings
from hinga.copy import DISCLAIMER
from hinga.habits import facts_match
from hinga.llm import Transport, complete_json
from hinga.schemas import (
    Citation,
    EntryAnalysis,
    HabitInsight,
    HabitStat,
    InsightDraft,
    JournalReflection,
    ReflectionDraft,
)
from hinga.textutil import PROMPTS, analysis_themes, detect_themes, first_sentence, mood_label

logger = logging.getLogger("hinga.agents")

REFLECTION_SYSTEM = """You are the reflection desk inside Hinga, a journaling tool.
You are not a clinician. You do not diagnose, treat, prescribe, or explain causes.
Write from the journal note and the retrieved notes only. Do not add facts.
Return one JSON object with keys summary, themes, pattern_note, gentle_prompt, citation_ids.
summary: one or two sentences restating the note.
themes: up to 4 short lowercase labels from the note.
pattern_note: one sentence. If retrieved notes are listed, mention one by its date. If none, say nothing earlier is close enough to cite.
gentle_prompt: one noticing question, not advice to fix themselves.
citation_ids: ids copied from the retrieved notes. Empty if none. Never invent an id.
Do not use the words diagnosis, prescribe, disorder, treatment plan, or "this caused".
"""

INSIGHT_SYSTEM = """You are the habit desk inside Hinga. You are not a clinician.
You are given habit counts that were already computed. Copy those counts exactly into habits.
You may write observation and one_small_step.
observation: one or two sentences using only the counts and, if present, the sleep_note.
If sleep_note is null, do not mention sleep. Never call a pattern a cause.
one_small_step: one concrete next action copied from the lowest habit's intention. No medical advice.
Return JSON with keys observation, one_small_step, habits.
Each habit has habit_id, name, done_days, window_days, streak. Copy them exactly.
"""


@dataclass(frozen=True)
class RetrievedNote:
    entry_id: str
    date_label: str
    excerpt: str
    overlap: float
    themes: list[str]


def mock_analysis(body: str, mood: int) -> EntryAnalysis:
    return EntryAnalysis(
        mood=mood,
        sentiment=mood_label(mood),  # type: ignore[arg-type]
        themes=analysis_themes(body),  # type: ignore[arg-type]
    )


def analyze(
    body: str,
    mood: int,
    settings: Settings,
    transport: Transport | None = None,
) -> tuple[EntryAnalysis | None, str]:
    """One schema repair, then give up and mark the note unanalyzed. The note stays."""
    offline = mock_analysis(body, mood)
    if settings.llm_mode != "llm" and transport is None:
        return offline, "analyzed"
    system = (
        "Return JSON with keys mood, sentiment, themes. "
        "mood is an integer 1 to 5. sentiment is one of heavy, low, steady, light, bright. "
        "themes is a list drawn only from: sleep, body, work, people, food, outside, home, focus. "
        "Do not diagnose."
    )
    try:
        draft = complete_json(
            settings,
            system,
            body,
            EntryAnalysis,
            transport=transport,
        )
        # The check-in owns the mood. The model does not.
        return draft.model_copy(update={"mood": mood, "sentiment": mood_label(mood)}), "analyzed"
    except Exception as exc:
        logger.warning("analysis stored as unanalyzed: %s", type(exc).__name__)
        return None, "unanalyzed"


def build_mock_reflection(body: str, mood: int, retrieved: list[RetrievedNote]) -> JournalReflection:
    from hinga.textutil import mood_label

    themes = detect_themes(body)
    summary = first_sentence(body) or "You saved a note."
    if retrieved:
        top = retrieved[0]
        shared = top.themes[0] if top.themes else "the same ground"
        pattern = (
            f"A note from {top.date_label} overlaps this one ({top.overlap:.2f}) "
            f"and also sits with {shared}."
        )
        citations = [
            Citation(
                entry_id=note.entry_id,
                date_label=note.date_label,
                excerpt=note.excerpt,
                overlap=round(note.overlap, 2),
            )
            for note in retrieved[:3]
        ]
    else:
        pattern = "Nothing earlier is close enough to cite."
        citations = []
    prompt_key = themes[0] if themes else "default"
    return JournalReflection(
        summary=summary,
        mood_label=mood_label(mood),  # type: ignore[arg-type]
        themes=themes,
        pattern_note=pattern,
        gentle_prompt=PROMPTS[prompt_key],
        citations=citations,
        disclaimer=DISCLAIMER,
        source="mock",
        fallback=False,
    )


def reflection_from_draft(
    draft: ReflectionDraft,
    mood: int,
    retrieved: list[RetrievedNote],
    *,
    source: str,
    fallback: bool,
) -> JournalReflection:
    from hinga.textutil import mood_label

    by_id = {note.entry_id: note for note in retrieved}
    citations: list[Citation] = []
    for entry_id in draft.citation_ids:
        note = by_id.get(entry_id)
        if note is None:
            continue
        citations.append(
            Citation(
                entry_id=note.entry_id,
                date_label=note.date_label,
                excerpt=note.excerpt,
                overlap=round(note.overlap, 2),
            )
        )
    themes = draft.themes or detect_themes(draft.summary)
    return JournalReflection(
        summary=draft.summary,
        mood_label=mood_label(mood),  # type: ignore[arg-type]
        themes=themes[:4],
        pattern_note=draft.pattern_note,
        gentle_prompt=draft.gentle_prompt,
        citations=citations[:3],
        disclaimer=DISCLAIMER,
        source=source,  # type: ignore[arg-type]
        fallback=fallback,
    )


def _reflection_user(body: str, retrieved: list[RetrievedNote]) -> str:
    lines = [f"Journal note:\n{body}", "", "Retrieved notes (cite only these ids):"]
    if not retrieved:
        lines.append("(none)")
    for note in retrieved:
        lines.append(
            f"- id={note.entry_id} date={note.date_label} overlap={note.overlap:.2f} excerpt={note.excerpt}"
        )
    return "\n".join(lines)


def reflect(
    body: str,
    mood: int,
    retrieved: list[RetrievedNote],
    settings: Settings,
    transport: Transport | None = None,
) -> JournalReflection:
    offline = build_mock_reflection(body, mood, retrieved)
    if settings.llm_mode != "llm" and transport is None:
        return offline
    try:
        draft = complete_json(
            settings,
            REFLECTION_SYSTEM,
            _reflection_user(body, retrieved),
            ReflectionDraft,
            transport=transport,
        )
        return reflection_from_draft(draft, mood, retrieved, source="llm", fallback=False)
    except Exception as exc:
        logger.warning("reflection fell back to offline draft: %s", type(exc).__name__)
        return offline.model_copy(update={"fallback": True})


def build_mock_insight(
    stats: list[HabitStat],
    sleep_note: tuple[str, int] | None,
) -> HabitInsight:
    from hinga.habits import build_observation, one_small_step

    return HabitInsight(
        window_days=7,
        habits=stats,
        observation=build_observation(stats, sleep_note),
        one_small_step=one_small_step(stats),
        disclaimer=DISCLAIMER,
        source="mock",
        fallback=False,
    )


def _insight_user(stats: list[HabitStat], sleep_note: tuple[str, int] | None) -> str:
    payload = {
        "sleep_note": (
            None
            if sleep_note is None
            else {"habit_name": sleep_note[0], "missed_days_with_sleep_theme": sleep_note[1]}
        ),
        "habits": [
            {
                "habit_id": stat.habit_id,
                "name": stat.name,
                "intention": stat.intention,
                "done_days": stat.done_days,
                "window_days": stat.window_days,
                "streak": stat.streak,
            }
            for stat in stats
        ],
    }
    import json

    return "Fact sheet. Copy habit numbers exactly.\n" + json.dumps(payload, indent=2)


def explain_habits(
    stats: list[HabitStat],
    sleep_note: tuple[str, int] | None,
    settings: Settings,
    transport: Transport | None = None,
) -> HabitInsight:
    offline = build_mock_insight(stats, sleep_note)
    if settings.llm_mode != "llm" and transport is None:
        return offline
    try:
        draft = complete_json(
            settings,
            INSIGHT_SYSTEM,
            _insight_user(stats, sleep_note),
            InsightDraft,
            transport=transport,
        )
        if not facts_match(draft.habits, stats):
            raise ValueError("habit counts did not match the fact sheet")
        return HabitInsight(
            window_days=7,
            habits=stats,
            observation=draft.observation,
            one_small_step=draft.one_small_step,
            disclaimer=DISCLAIMER,
            source="llm",
            fallback=False,
        )
    except Exception as exc:
        logger.warning("habit insight fell back to offline draft: %s", type(exc).__name__)
        return offline.model_copy(update={"fallback": True})
