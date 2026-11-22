"""HTTP desk. One process serves the API and the pages."""

from __future__ import annotations

import hashlib
import hmac
import logging
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from hinga.config import Settings, load_settings
from hinga.copy import DISCLAIMER
from hinga.crypto import cipher_for
from hinga.db import directory_scope, init_db, make_engine, make_session_factory, user_scope
from hinga.models import User
from hinga.safety import PREVIEW_PHRASE, is_crisis, safety_payload
from hinga.seed import sample_note, seed
from hinga.services import (
    create_entry,
    delete_my_data,
    export_desk,
    get_entry,
    habit_board,
    list_entries,
    read_profile,
    search,
    toggle_habit,
)

logger = logging.getLogger("hinga")
STATIC = Path(__file__).resolve().parent / "static"
COOKIE = "fn_session"


class EntryIn(BaseModel):
    body: str = Field(min_length=1, max_length=8000)
    mood: int = Field(ge=1, le=5)

    @field_validator("body")
    @classmethod
    def _strip(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Write a few words first.")
        return text


class SessionIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=36)


class TurnIn(BaseModel):
    route: Literal["mindfulness", "journal", "habit", "insights"] = "journal"
    body: str = ""
    mood: int | None = Field(default=None, ge=1, le=5)

    @field_validator("body")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


def sign_user(user_id: str, secret: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), user_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{user_id}.{mac}"


def read_user(token: str, secret: str) -> str | None:
    if not token or "." not in token:
        return None
    user_id, mac = token.rsplit(".", 1)
    expected = hmac.new(secret.encode("utf-8"), user_id.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, expected):
        return None
    if not user_id or len(user_id) > 36:
        return None
    return user_id


def _personas(factory) -> list[dict[str, str]]:
    with directory_scope(factory) as session:
        rows = session.scalars(select(User)).all()
        people = [{"id": row.id, "display_name": row.display_name} for row in rows]
        order = {"maya": 0, "jonah": 1}
        people.sort(key=lambda person: (order.get(person["id"], 9), person["display_name"]))
        return people


def _public(settings: Settings, user: dict | None, personas: list[dict[str, str]]) -> dict:
    return {
        "user": user,
        "personas": personas,
        "disclaimer": DISCLAIMER,
        "llm_mode": settings.llm_mode,
        "llm_label": settings.llm_label,
        "embedding_mode": settings.embedding_mode,
        "database": settings.database_kind,
        "sample_note": sample_note(),
        "today": date.today().isoformat(),
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    factory = make_session_factory(engine)
    postgres = settings.database_kind == "postgres"
    cipher = cipher_for(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        seed(factory, postgres=postgres, cipher=cipher)
        yield

    app = FastAPI(title="Hinga", lifespan=lifespan)
    app.state.settings = settings
    app.state.factory = factory
    app.state.postgres = postgres
    app.state.cipher = cipher
    app.state.llm_transport = None

    def session_dependency(request: Request):
        token = request.cookies.get(COOKIE, "")
        user_id = read_user(token, settings.session_secret)
        if not user_id:
            raise HTTPException(status_code=401, detail="Choose a person to open the desk.")
        with user_scope(factory, user_id, postgres=postgres) as session:
            user = session.get(User, user_id)
            if user is None:
                raise HTTPException(status_code=401, detail="Choose a person to open the desk.")
            yield session

    @app.exception_handler(PermissionError)
    async def _permission(_request: Request, _exc: PermissionError):
        return JSONResponse(status_code=403, content={"detail": "Those notes aren't on this desk."})

    @app.get("/api/health")
    def health():
        return {
            "ok": True,
            "llm_mode": settings.llm_mode,
            "llm_label": settings.llm_label,
            "embedding_mode": settings.embedding_mode,
            "database": settings.database_kind,
            "graph": ["safety_guard", "memory", "mindfulness", "journal", "habit", "insights"],
        }

    @app.get("/api/bootstrap")
    def bootstrap(request: Request):
        personas = _personas(factory)
        token = request.cookies.get(COOKIE, "")
        user_id = read_user(token, settings.session_secret)
        user = None
        if user_id:
            with user_scope(factory, user_id, postgres=postgres) as session:
                row = session.get(User, user_id)
                if row is not None:
                    user = {
                        "id": row.id,
                        "display_name": row.display_name,
                        "profile": read_profile(session, cipher),
                    }
        return _public(settings, user, personas)

    @app.post("/api/session")
    def open_session(body: SessionIn):
        with user_scope(factory, body.user_id, postgres=postgres) as session:
            row = session.get(User, body.user_id)
            if row is None:
                raise HTTPException(status_code=404, detail="That person isn't on this desk.")
            user = {
                "id": row.id,
                "display_name": row.display_name,
                "profile": read_profile(session, cipher),
            }
        payload = _public(settings, user, _personas(factory))
        response = JSONResponse(payload)
        response.set_cookie(
            COOKIE,
            sign_user(user["id"], settings.session_secret),
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 30,
            path="/",
        )
        return response

    @app.get("/api/entries")
    def entries(session: Session = Depends(session_dependency)):
        return {"entries": list_entries(session, cipher)}

    @app.get("/api/entries/{entry_id}")
    def entry(entry_id: str, session: Session = Depends(session_dependency)):
        found = get_entry(session, cipher, entry_id)
        if found is None:
            raise HTTPException(status_code=404, detail="That page isn't on this desk.")
        return found

    @app.post("/api/entries")
    def write_entry(body: EntryIn, request: Request, session: Session = Depends(session_dependency)):
        return create_entry(
            session,
            settings,
            cipher,
            body=body.body,
            mood=body.mood,
            route="journal",
            transport=request.app.state.llm_transport,
        )

    @app.post("/api/turn")
    def turn(body: TurnIn, request: Request, session: Session = Depends(session_dependency)):
        if body.route in {"journal", "mindfulness"} and body.mood is None:
            raise HTTPException(status_code=400, detail="Pick a mark for how the day feels.")
        if body.route == "journal" and not body.body:
            raise HTTPException(status_code=400, detail="Write a few words first.")
        return create_entry(
            session,
            settings,
            cipher,
            body=body.body,
            mood=body.mood or 3,
            route=body.route,
            transport=request.app.state.llm_transport,
        )

    @app.get("/api/me/export")
    def export_mine(session: Session = Depends(session_dependency)):
        return export_desk(session, cipher)

    @app.post("/api/me/delete")
    def delete_mine(session: Session = Depends(session_dependency)):
        return delete_my_data(session)

    @app.get("/api/search")
    def search_notes(q: str = "", session: Session = Depends(session_dependency)):
        query = " ".join(q.split())
        if not query:
            raise HTTPException(status_code=400, detail="Type a phrase to recall.")
        if len(query) > 200:
            raise HTTPException(status_code=400, detail="Keep the phrase under 200 characters.")
        return search(session, settings, cipher, query)

    @app.get("/api/habits")
    def habits(request: Request, session: Session = Depends(session_dependency)):
        return habit_board(session, settings, cipher, transport=request.app.state.llm_transport)

    @app.post("/api/habits/{habit_id}/toggle")
    def toggle(habit_id: str, request: Request, session: Session = Depends(session_dependency)):
        changed = toggle_habit(session, habit_id)
        if changed is None:
            raise HTTPException(status_code=404, detail="That habit isn't on this desk.")
        board = habit_board(session, settings, cipher, transport=request.app.state.llm_transport)
        return {"done_today": changed, "insight": board}

    @app.get("/api/resources")
    def resources(stored: bool = True):
        return safety_payload(stored=stored).model_dump()

    @app.post("/api/safety/preview")
    def preview_safety(session: Session = Depends(session_dependency)):
        # Touch the session so an unsigned caller cannot open the screen,
        # and prove the real detector still matches the server-side phrase.
        if session.info.get("user_id") is None or not is_crisis(PREVIEW_PHRASE):
            raise HTTPException(status_code=500, detail="The safety screen is misconfigured.")
        return safety_payload(stored=False).model_dump()

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
