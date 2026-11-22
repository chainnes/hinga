"""Sixty days for two fictional people. Generated, not a diary of a real person."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta

from cryptography.fernet import Fernet
from sqlalchemy.orm import sessionmaker

from hinga.agents import RetrievedNote, build_mock_reflection, mock_analysis
from hinga.crypto import seal
from hinga.db import user_scope
from hinga.embeddings import local_embed
from hinga.models import Habit, HabitLog, JournalEntry, Profile, User
from hinga.retrieval import rank
from hinga.textutil import date_label, detect_themes, excerpt

HISTORY_DAYS = 60
SAMPLE_NOTE = (
    "The train stalled again and I ate at my desk. "
    "My shoulders stayed up until I walked the long way home."
)

PROFILES = {
    "maya": {
        "name": "Maya Ellison",
        "values": "Leave the desk at lunch, and treat sleep as a boundary.",
        "goals": "Lights out by 11 on more nights than not.",
        "tone": "Plain and specific.",
    },
    "jonah": {
        "name": "Jonah Reyes",
        "values": "Be a steady parent, and keep one person outside this apartment.",
        "goals": "Step outside once a day.",
        "tone": "Short. No pep talk.",
    },
}

HABITS = {
    "maya": (
        ("walk", "Morning walk", "Ten minutes outside before opening the laptop.", "Stand outside for two minutes.", "Leave the desk at lunch, and treat sleep as a boundary."),
        ("lights", "Lights out by 11", "Phone charges in the other room.", "Close the laptop at 11.", "Leave the desk at lunch, and treat sleep as a boundary."),
        ("lunch", "Lunch away from the desk", "Eat somewhere that is not the keyboard.", "Step away from the desk before the first bite.", "Leave the desk at lunch, and treat sleep as a boundary."),
    ),
    "jonah": (
        ("outside", "Step outside", "Ten minutes of air, with the baby or without.", "Open the door and stand in it.", "Be a steady parent, and keep one person outside this apartment."),
        ("stretch", "Stretch", "Five minutes on the floor before the late feed.", "One shoulder roll before the late feed.", "Be a steady parent, and keep one person outside this apartment."),
        ("sister", "Text a friend", "One message to someone who isn't in this apartment.", "Send one sentence.", "Be a steady parent, and keep one person outside this apartment."),
    ),
}

_MAYA_CYCLE = (
    "Quiet evening. I cooked and the lights were out on time. I slept.",
    "Walked before work and kept my shoulders down on purpose.",
    "Lunch in the park with Sam. Grateful for the shade.",
    "The meeting ran long and I answered email until late.",
    "Heavy afternoon. I skipped the walk and my shoulders stayed tight.",
)
_JONAH_CYCLE = (
    "The baby woke twice. I stood in the dark and counted breaths until he settled.",
    "I texted my sister after the baby finally slept a stretch.",
    "Stepped outside with the baby for ten minutes. The air helped.",
    "My back was sore and I skipped the stretch. The baby napped on me.",
    "A small win: the baby napped in the crib and I ate sitting down.",
)


def note_for(persona: str, days_ago: int) -> tuple[int, str]:
    if persona == "maya" and days_ago == 1:
        return 2, (
            "I slept badly, then the train stalled outside the station and I ate lunch at my desk. "
            "My shoulders stayed up until I walked the long way home."
        )
    if persona == "maya" and days_ago == 3:
        return 2, "Awake at 2 again, scrolling. I was tired enough to skip the walk and leave the lights on."
    if persona == "maya" and days_ago == 4:
        return 3, "The meeting ran long and lunch happened at the desk again. I did get the walk in before it."
    if persona == "jonah" and days_ago == 1:
        return 2, "I was awake after the 1am feed. The baby had been up, and I put the phone in a drawer."
    cycle = _MAYA_CYCLE if persona == "maya" else _JONAH_CYCLE
    moods = (3, 4, 4, 2, 2)
    index = days_ago % 5
    return moods[index], cycle[index]


def is_done(persona: str, key: str, days_ago: int) -> bool:
    """Deterministic habit marks. Today (0) is never pre-filled."""
    if days_ago <= 0 or days_ago > HISTORY_DAYS:
        return False
    if persona == "maya":
        if key == "walk":
            return days_ago % 3 != 0
        if key == "lights":
            return days_ago not in {1, 2, 3, 4}
        if key == "lunch":
            return days_ago == 6 or (days_ago > 6 and days_ago % 4 == 0)
    if persona == "jonah":
        if key == "outside":
            return days_ago % 2 != 0
        if key == "stretch":
            return days_ago not in {1, 2, 3, 4}
        if key == "sister":
            return days_ago % 5 == 1
    return False


def done_dates(persona: str, key: str, today: date) -> set[date]:
    return {
        today - timedelta(days=days_ago)
        for days_ago in range(1, HISTORY_DAYS + 1)
        if is_done(persona, key, days_ago)
    }


def seed(factory: sessionmaker, *, postgres: bool, cipher: Fernet, today: date | None = None) -> None:
    today = today or date.today()
    for persona, profile in PROFILES.items():
        with user_scope(factory, persona, postgres=postgres) as session:
            if session.get(User, persona) is not None:
                continue
            session.add(User(id=persona, display_name=profile["name"]))
            session.add(
                Profile(
                    user_id=persona,
                    values_sealed=seal(profile["values"], cipher),
                    goals_sealed=seal(profile["goals"], cipher),
                    tone_sealed=seal(profile["tone"], cipher),
                )
            )
            for key, name, intention, small, value_link in HABITS[persona]:
                habit_id = f"{persona}-{key}"
                session.add(
                    Habit(
                        id=habit_id,
                        user_id=persona,
                        name=name,
                        intention=intention,
                        intention_small=small,
                        value_link=value_link,
                    )
                )
                for days_ago in range(1, HISTORY_DAYS + 1):
                    if not is_done(persona, key, days_ago):
                        continue
                    logged = today - timedelta(days=days_ago)
                    session.add(
                        HabitLog(
                            id=f"{habit_id}-{logged.isoformat()}",
                            user_id=persona,
                            habit_id=habit_id,
                            logged_on=logged,
                        )
                    )
            written: list[JournalEntry] = []
            for days_ago in range(HISTORY_DAYS, 0, -1):
                mood, plain = note_for(persona, days_ago)
                moment = datetime.combine(today - timedelta(days=days_ago), time(21, 0))
                vector = local_embed(plain)
                reflection = build_mock_reflection(plain, mood, _retrieve(written, plain))
                analysis = mock_analysis(plain, mood)
                _remember(f"{persona}-d{days_ago}", plain)
                entry = JournalEntry(
                    id=f"{persona}-d{days_ago}",
                    user_id=persona,
                    body=seal(plain, cipher),
                    mood=mood,
                    created_at=moment,
                    embedding_json=json.dumps(vector),
                    embedding_space="local",
                    reflection_json=seal(reflection.model_dump_json(), cipher),
                    analysis_json=seal(analysis.model_dump_json(), cipher),
                    analysis_status="analyzed",
                    safety_hold=False,
                )
                session.add(entry)
                written.append(entry)


def _retrieve(previous: list[JournalEntry], body: str) -> list[RetrievedNote]:
    """Rank against plaintext held on the in-memory copies during seeding.

    Seeded rows store ciphertext in `body`, so the retrieval excerpt uses the
    note we just wrote, kept beside the row for this pass only.
    """
    vector = local_embed(body)
    ranked = rank(previous, vector, limit=3)
    notes: list[RetrievedNote] = []
    for hit in ranked:
        plain = _PLAIN.get(hit.item_id)
        entry = next(item for item in previous if item.id == hit.item_id)
        if plain is None:
            continue
        notes.append(
            RetrievedNote(
                entry_id=entry.id,
                date_label=date_label(entry.created_at),
                excerpt=excerpt(plain),
                overlap=hit.overlap,
                themes=detect_themes(plain),
            )
        )
    return notes


_PLAIN: dict[str, str] = {}


def _remember(entry_id: str, plain: str) -> None:
    _PLAIN[entry_id] = plain


def sample_note() -> str:
    return SAMPLE_NOTE
