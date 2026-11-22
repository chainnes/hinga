"""Sessions that refuse to read or write another person's notes.

On Postgres the same request also sets `app.user_id` for the row-level
security policies in db/postgres_rls.sql. On SQLite those policies do not
exist, so this scope is the isolation.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event, false, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker, with_loader_criteria

from hinga.models import Base, Habit, HabitLog, JournalEntry, Profile, User

PRIVATE_MODELS = (JournalEntry, Habit, HabitLog, Profile)
_GUARDS_INSTALLED = False


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite:///"):
        path = url.removeprefix("sqlite:///")
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def install_guards() -> None:
    global _GUARDS_INSTALLED
    if _GUARDS_INSTALLED:
        return
    _GUARDS_INSTALLED = True

    @event.listens_for(Session, "do_orm_execute")
    def _scope_select(state):
        if not state.is_select:
            return
        session = state.session
        if session.info.get("persona_directory"):
            state.statement = state.statement.options(
                *[
                    with_loader_criteria(model, false(), include_aliases=True)
                    for model in PRIVATE_MODELS
                ]
            )
            return
        user_id = session.info.get("user_id")
        if not user_id:
            raise PermissionError("refusing unscoped read")
        state.statement = state.statement.options(
            *[
                with_loader_criteria(model, model.user_id == user_id, include_aliases=True)
                for model in PRIVATE_MODELS
            ]
        )

    @event.listens_for(Session, "before_flush")
    def _scope_write(session, flush_context, instances):
        pending = list(session.new) + list(session.dirty) + list(session.deleted)
        if session.info.get("persona_directory"):
            if pending:
                raise PermissionError("persona directory is read-only")
            return
        user_id = session.info.get("user_id")
        if not user_id:
            raise PermissionError("refusing unscoped write")
        for obj in pending:
            if isinstance(obj, User) and obj.id != user_id:
                raise PermissionError("cross-user write blocked")
            owner = getattr(obj, "user_id", None)
            if owner is not None and owner != user_id:
                raise PermissionError("cross-user write blocked")


@contextmanager
def user_scope(factory: sessionmaker[Session], user_id: str, *, postgres: bool) -> Iterator[Session]:
    install_guards()
    session = factory()
    session.info["user_id"] = user_id
    try:
        if postgres:
            session.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": user_id})
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def directory_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Read display names. Private tables are forced empty in this scope."""
    install_guards()
    session = factory()
    session.info["persona_directory"] = True
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
