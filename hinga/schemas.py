"""Schemas the agents must satisfy. Mood and habit counts are not theirs to invent."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from hinga.copy import DISCLAIMER

BANNED_FRAGMENTS = (
    "diagnos",
    "prescrib",
    "treatment plan",
    "disorder",
    "you have depression",
    "you have anxiety",
    "this caused",
    "caused your",
    "because you missed",
)


def reject_clinical_claims(value: str) -> str:
    lowered = value.lower()
    for fragment in BANNED_FRAGMENTS:
        if fragment in lowered:
            raise ValueError(f"clinical or causal claim: {fragment}")
    return value.strip()


class Citation(BaseModel):
    entry_id: str
    date_label: str
    excerpt: str
    overlap: float = Field(ge=0, le=1)


class JournalReflection(BaseModel):
    summary: str = Field(min_length=1, max_length=400)
    mood_label: Literal["heavy", "low", "steady", "light", "bright"]
    themes: list[str] = Field(default_factory=list, max_length=4)
    pattern_note: str = Field(min_length=1, max_length=400)
    gentle_prompt: str = Field(min_length=1, max_length=280)
    citations: list[Citation] = Field(default_factory=list, max_length=3)
    disclaimer: str
    source: Literal["mock", "llm"]
    fallback: bool = False

    @field_validator("summary", "pattern_note", "gentle_prompt")
    @classmethod
    def _grounded(cls, value: str) -> str:
        return reject_clinical_claims(value)


class ReflectionDraft(BaseModel):
    """What the model is allowed to write. Citations and mood are filled in by code."""

    summary: str = Field(min_length=1, max_length=400)
    themes: list[str] = Field(default_factory=list, max_length=4)
    pattern_note: str = Field(min_length=1, max_length=400)
    gentle_prompt: str = Field(min_length=1, max_length=280)
    citation_ids: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("summary", "pattern_note", "gentle_prompt")
    @classmethod
    def _grounded(cls, value: str) -> str:
        return reject_clinical_claims(value)

    @field_validator("themes")
    @classmethod
    def _themes(cls, value: list[str]) -> list[str]:
        cleaned = []
        for item in value:
            text = " ".join(item.lower().split())
            if text and len(text) <= 40:
                cleaned.append(text)
        return cleaned[:4]


class HabitDay(BaseModel):
    date: str
    label: str
    done: bool
    is_today: bool


class HabitStat(BaseModel):
    habit_id: str
    name: str
    intention: str
    done_days: int = Field(ge=0)
    window_days: int = Field(ge=1)
    streak: int = Field(ge=0)
    days: list[HabitDay] = Field(default_factory=list)
    shrunk: bool = False
    reframe: str | None = None


class HabitStatDraft(BaseModel):
    habit_id: str
    name: str
    done_days: int = Field(ge=0)
    window_days: int = Field(ge=1)
    streak: int = Field(ge=0)


class HabitInsight(BaseModel):
    window_days: int
    habits: list[HabitStat]
    observation: str = Field(min_length=1, max_length=700)
    one_small_step: str = Field(min_length=1, max_length=280)
    week_note: str = ""
    disclaimer: str = DISCLAIMER
    source: Literal["mock", "llm"]
    fallback: bool = False

    @field_validator("observation", "one_small_step", "week_note")
    @classmethod
    def _grounded(cls, value: str) -> str:
        return reject_clinical_claims(value)


class InsightDraft(BaseModel):
    observation: str = Field(min_length=1, max_length=600)
    one_small_step: str = Field(min_length=1, max_length=280)
    habits: list[HabitStatDraft]

    @field_validator("observation", "one_small_step")
    @classmethod
    def _grounded(cls, value: str) -> str:
        return reject_clinical_claims(value)


FIXED_THEMES = ("sleep", "body", "work", "people", "food", "outside", "home", "focus")


class EntryAnalysis(BaseModel):
    """Typed reading of one note. Mood is the check-in. Themes come from a fixed list."""

    mood: int = Field(ge=1, le=5)
    sentiment: Literal["heavy", "low", "steady", "light", "bright"]
    themes: list[Literal["sleep", "body", "work", "people", "food", "outside", "home", "focus"]] = Field(
        default_factory=list,
        max_length=4,
    )


class Resource(BaseModel):
    name: str
    detail: str
    href: str


class SafetyHold(BaseModel):
    safety: Literal["hold"] = "hold"
    stored: bool
    title: str
    message: str
    resources: list[Resource]
    disclaimer: str = DISCLAIMER
