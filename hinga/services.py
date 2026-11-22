"""Use-cases shared by the HTTP routes. Every query runs inside a user scope."""

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from datetime import date, datetime

from cryptography.fernet import Fernet
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from hinga.agents import RetrievedNote, analyze, explain_habits
from hinga.config import Settings
from hinga.crypto import seal, unseal
from hinga.embeddings import local_embed, openai_embed
from hinga.graph import invoke_desk
from hinga.habits import (
    adapt_intention,
    build_stat,
    guilt_free_reframe,
    strongest_sleep_note,
    weekly_observation,
)
from hinga.llm import Transport
from hinga.models import Habit, HabitLog, JournalEntry, Profile
from hinga.retrieval import rank
from hinga.textutil import analysis_themes, date_label, detect_themes, excerpt, mood_label

logger = logging.getLogger("hinga.services")


def _open_json(raw: str | None, cipher: Fernet) -> dict | None:
    if not raw:
        return None
    try:
        data = json.loads(unseal(raw, cipher))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def serialize_entry(entry: JournalEntry, cipher: Fernet) -> dict:
    held = bool(entry.safety_hold) or entry.analysis_status == "held"
    return {
        "id": entry.id,
        "body": unseal(entry.body, cipher),
        "mood": entry.mood,
        "mood_label": mood_label(entry.mood),
        "created_at": entry.created_at.isoformat(timespec="minutes"),
        "date_label": date_label(entry.created_at),
        "safety_hold": held,
        "analysis_status": entry.analysis_status,
        "analysis": None if held else _open_json(entry.analysis_json, cipher),
        "reflection": None if held else _open_json(entry.reflection_json, cipher),
    }


def list_entries(session: Session, cipher: Fernet) -> list[dict]:
    rows = session.scalars(select(JournalEntry).order_by(JournalEntry.created_at.desc())).all()
    return [serialize_entry(row, cipher) for row in rows]


def get_entry(session: Session, cipher: Fernet, entry_id: str) -> dict | None:
    row = session.get(JournalEntry, entry_id)
    user_id = session.info.get("user_id")
    if row is None or row.user_id != user_id:
        return None
    return serialize_entry(row, cipher)


def read_profile(session: Session, cipher: Fernet) -> dict:
    row = session.get(Profile, session.info.get("user_id"))
    if row is None:
        return {}
    return {
        "values": unseal(row.values_sealed, cipher),
        "goals": unseal(row.goals_sealed, cipher),
        "tone": unseal(row.tone_sealed, cipher),
    }


def _embed_new(text: str, settings: Settings) -> tuple[str, list[float]]:
    if settings.embedding_mode == "openai":
        try:
            vector = openai_embed(
                text,
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                model=settings.embedding_model,
            )
            return f"openai:{settings.embedding_model}", vector
        except Exception as exc:
            logger.warning("embedding provider failed, storing a local vector: %s", type(exc).__name__)
    return "local", local_embed(text)


def _query_vector(text: str, space: str, settings: Settings) -> list[float] | None:
    if space == "local":
        return local_embed(text)
    if space.startswith("openai:"):
        try:
            model = space.split(":", 1)[1] or settings.embedding_model
            return openai_embed(
                text,
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                model=model,
            )
        except Exception as exc:
            logger.warning("could not embed the query in %s: %s", space, type(exc).__name__)
            return None
    return None


def recall(
    session: Session,
    query: str,
    settings: Settings,
    cipher: Fernet,
    *,
    limit: int = 3,
) -> list[RetrievedNote]:
    rows = session.scalars(
        select(JournalEntry).where(JournalEntry.safety_hold.is_(False))
    ).all()
    grouped: dict[str, list[JournalEntry]] = defaultdict(list)
    for row in rows:
        grouped[row.embedding_space or "local"].append(row)
    hits: list[tuple[JournalEntry, float]] = []
    for space, group in grouped.items():
        vector = _query_vector(query, space, settings)
        if vector is None:
            continue
        by_id = {row.id: row for row in group}
        for ranked in rank(group, vector, limit=limit):
            hits.append((by_id[ranked.item_id], ranked.overlap))
    hits.sort(key=lambda pair: pair[1], reverse=True)
    notes: list[RetrievedNote] = []
    for row, overlap in hits[:limit]:
        plain = unseal(row.body, cipher)
        notes.append(
            RetrievedNote(
                entry_id=row.id,
                date_label=date_label(row.created_at),
                excerpt=excerpt(plain),
                overlap=overlap,
                themes=detect_themes(plain),
            )
        )
    return notes


def week_note(session: Session, cipher: Fernet, today: date | None = None) -> str:
    today = today or date.today()
    rows = session.scalars(select(JournalEntry).where(JournalEntry.safety_hold.is_(False))).all()
    this_week: list[int] = []
    last_week: list[int] = []
    themes: list[str] = []
    for row in rows:
        age = (today - row.created_at.date()).days
        if age < 0 or age > 13:
            continue
        if age <= 6:
            this_week.append(row.mood)
            themes.extend(analysis_themes(unseal(row.body, cipher)))
        else:
            last_week.append(row.mood)
    return weekly_observation(this_week, last_week, themes)


def build_memory(session: Session, settings: Settings, cipher: Fernet, text: str) -> dict:
    retrieved = []
    if text.strip():
        retrieved = [note.__dict__ for note in recall(session, text, settings, cipher, limit=3)]
    stats, _sleep, _dates = _board(session, cipher, date.today())
    return {
        "profile": read_profile(session, cipher),
        "retrieved": retrieved,
        "habits": [stat.model_dump() for stat in stats],
        "week_note": week_note(session, cipher),
    }


def _store(
    session: Session,
    cipher: Fernet,
    settings: Settings,
    *,
    body: str,
    mood: int,
    result: dict,
    now: datetime | None,
    transport: Transport | None = None,
) -> JournalEntry:
    moment = now or datetime.now().replace(microsecond=0)
    held = result.get("route") == "safety_guard" or result.get("analysis_status") == "held"
    reflection = result.get("reflection")
    analysis = result.get("analysis")
    if held:
        status = "held"
    elif result.get("analysis_status"):
        status = result["analysis_status"]
    else:
        analysis, status = analyze(body, mood, settings, transport=transport)
    if held:
        space, vector_json = "none", "[]"
    else:
        space, vector = _embed_new(body, settings)
        vector_json = json.dumps(vector)
    entry = JournalEntry(
        id=str(uuid.uuid4()),
        user_id=session.info["user_id"],
        body=seal(body, cipher),
        mood=mood,
        created_at=moment,
        embedding_json=vector_json,
        embedding_space=space,
        reflection_json=None if not reflection else seal(json.dumps(reflection), cipher),
        analysis_json=None if not analysis else seal(json.dumps(analysis), cipher),
        analysis_status=status,
        safety_hold=held,
    )
    session.add(entry)
    session.flush()
    return entry


def create_entry(
    session: Session,
    settings: Settings,
    cipher: Fernet,
    *,
    body: str,
    mood: int,
    route: str = "journal",
    transport: Transport | None = None,
    now: datetime | None = None,
) -> dict:
    def load_memory(text: str) -> dict:
        return build_memory(session, settings, cipher, text)

    result = invoke_desk(
        text=body,
        mood=mood,
        route=route,
        load_memory=load_memory,
        settings=settings,
        transport=transport,
    )
    if body.strip():
        entry = _store(
            session,
            cipher,
            settings,
            body=body,
            mood=mood,
            result=result,
            now=now,
            transport=transport,
        )
        result["entry"] = serialize_entry(entry, cipher)
    else:
        result["entry"] = None
    result.setdefault("safety", None)
    result.setdefault("reflection", None)
    return result


def search(session: Session, settings: Settings, cipher: Fernet, query: str) -> dict:
    notes = recall(session, query, settings, cipher, limit=5)
    return {
        "query": query,
        "embedding_mode": settings.embedding_mode,
        "results": [
            {
                "id": note.entry_id,
                "date_label": note.date_label,
                "excerpt": note.excerpt,
                "overlap": round(note.overlap, 2),
                "themes": note.themes,
            }
            for note in notes
        ],
    }


def _board(session: Session, cipher: Fernet, today: date) -> tuple[list, tuple[str, int] | None, dict[date, list[str]]]:
    habits = session.scalars(select(Habit).order_by(Habit.name)).all()
    logs = session.scalars(select(HabitLog)).all()
    done_by_habit: dict[str, set[date]] = defaultdict(set)
    for log in logs:
        done_by_habit[log.habit_id].add(log.logged_on)
    stats = []
    for habit in habits:
        done = done_by_habit.get(habit.id, set())
        intention, shrunk = adapt_intention(habit.intention, habit.intention_small or "", done, today)
        stat = build_stat(
            habit_id=habit.id,
            name=habit.name,
            intention=intention,
            done_dates=done,
            today=today,
        )
        stats.append(
            stat.model_copy(
                update={
                    "shrunk": shrunk,
                    "reframe": guilt_free_reframe(habit.name, done, today),
                }
            )
        )
    entries = session.scalars(
        select(JournalEntry).where(JournalEntry.safety_hold.is_(False))
    ).all()
    by_date: dict[date, list[str]] = defaultdict(list)
    for entry in entries:
        by_date[entry.created_at.date()].append(unseal(entry.body, cipher))
    return stats, strongest_sleep_note(stats, by_date), by_date


def habit_board(
    session: Session,
    settings: Settings,
    cipher: Fernet,
    *,
    today: date | None = None,
    transport: Transport | None = None,
) -> dict:
    today = today or date.today()
    stats, sleep_note, _by_date = _board(session, cipher, today)
    insight = explain_habits(stats, sleep_note, settings, transport=transport)
    insight = insight.model_copy(update={"week_note": week_note(session, cipher, today)})
    return insight.model_dump()


def export_desk(session: Session, cipher: Fernet) -> dict:
    habits = session.scalars(select(Habit).order_by(Habit.name)).all()
    return {
        "user_id": session.info.get("user_id"),
        "profile": read_profile(session, cipher),
        "entries": list_entries(session, cipher),
        "habits": [
            {
                "id": habit.id,
                "name": habit.name,
                "intention": habit.intention,
                "intention_small": habit.intention_small,
                "value_link": habit.value_link,
            }
            for habit in habits
        ],
    }


def delete_my_data(session: Session) -> dict:
    user_id = session.info.get("user_id")
    if not user_id:
        raise PermissionError("refusing unscoped write")
    for model in (JournalEntry, HabitLog, Habit, Profile):
        session.execute(delete(model).where(model.user_id == user_id))
    return {"deleted": True, "user_id": user_id}


def toggle_habit(session: Session, habit_id: str, today: date | None = None) -> bool | None:
    today = today or date.today()
    habit = session.get(Habit, habit_id)
    user_id = session.info.get("user_id")
    if habit is None or habit.user_id != user_id:
        return None
    existing = session.scalars(
        select(HabitLog).where(HabitLog.habit_id == habit_id, HabitLog.logged_on == today)
    ).first()
    if existing is not None:
        session.delete(existing)
        return False
    session.add(
        HabitLog(
            id=f"{habit_id}-{today.isoformat()}-t",
            user_id=user_id,
            habit_id=habit_id,
            logged_on=today,
        )
    )
    return True
