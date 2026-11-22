import json
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from hinga.db import directory_scope, user_scope
from hinga.models import JournalEntry
from hinga.habits import current_streak
from hinga.seed import HISTORY_DAYS, done_dates


def _ids(client, user_id):
    opened = client.post("/api/session", json={"user_id": user_id})
    assert opened.status_code == 200
    payload = client.get("/api/entries").json()
    return {entry["id"] for entry in payload["entries"]}


def test_health_and_disclaimer(client):
    health = client.get("/api/health").json()
    assert health["ok"] is True
    assert health["llm_mode"] == "mock"
    assert health["database"] == "sqlite"
    boot = client.get("/api/bootstrap").json()
    assert "not medical advice" in boot["disclaimer"].lower()
    assert {person["id"] for person in boot["personas"]} == {"maya", "jonah"}


def test_pages_are_isolated_and_search_stays_on_one_desk(client):
    maya_ids = _ids(client, "maya")
    jonah_ids = _ids(client, "jonah")
    assert maya_ids.isdisjoint(jonah_ids)
    assert len(maya_ids) == HISTORY_DAYS
    assert len(jonah_ids) == HISTORY_DAYS

    client.post("/api/session", json={"user_id": "jonah"})
    baby = client.get("/api/search", params={"q": "baby"}).json()
    assert baby["results"]
    assert {hit["id"] for hit in baby["results"]} <= jonah_ids

    client.post("/api/session", json={"user_id": "maya"})
    desk = client.get("/api/search", params={"q": "desk lunch"}).json()
    assert desk["results"]
    assert {hit["id"] for hit in desk["results"]} <= maya_ids
    stolen = next(iter(jonah_ids))
    assert client.get(f"/api/entries/{stolen}").status_code == 404


def test_unscoped_reads_and_cross_writes_are_refused(client):
    factory = client.app.state.factory
    bare = factory()
    with pytest.raises(PermissionError):
        bare.scalars(select(JournalEntry)).all()
    bare.close()

    with directory_scope(factory) as session:
        assert session.scalars(select(JournalEntry)).all() == []

    with pytest.raises(PermissionError):
        with user_scope(factory, "maya", postgres=False) as session:
            session.add(
                JournalEntry(
                    id="smuggled",
                    user_id="jonah",
                    body="This belongs on the other desk.",
                    mood=3,
                    created_at=date.today(),
                    embedding_json="[]",
                    embedding_space="local",
                    reflection_json=None,
                    safety_hold=False,
                )
            )
            session.flush()


def test_maya_habit_counts_come_from_code(client):
    today = date.today()
    board = client.get("/api/habits").json()
    by_name = {habit["name"]: habit for habit in board["habits"]}
    walk_done = done_dates("maya", "walk", today)
    window = {today - timedelta(days=offset) for offset in range(7)}
    assert by_name["Morning walk"]["done_days"] == len(walk_done & window)
    assert by_name["Morning walk"]["streak"] == current_streak(walk_done, today)
    assert by_name["Lights out by 11"]["streak"] == 0
    assert by_name["Lights out by 11"]["shrunk"] is True
    assert "verdict" in by_name["Lights out by 11"]["reframe"]
    assert "Not a cause." in board["observation"]
    assert "sleep" in board["observation"].lower()
    assert board["week_note"]
    assert board["source"] == "mock"
    assert "Lunch away from the desk" in board["one_small_step"]

    before = by_name["Lunch away from the desk"]["done_days"]
    toggled = client.post("/api/habits/maya-lunch/toggle")
    assert toggled.status_code == 200
    lunch = next(habit for habit in toggled.json()["insight"]["habits"] if habit["habit_id"] == "maya-lunch")
    assert lunch["done_days"] == before + 1

    client.post("/api/session", json={"user_id": "jonah"})
    blocked = client.post("/api/habits/maya-lunch/toggle")
    assert blocked.status_code == 404


def test_crisis_note_is_saved_without_a_reflection_or_a_model_call(client):
    def explode(_messages):
        raise AssertionError("the model must not see a held note")

    client.app.state.llm_transport = explode
    unique = "zephyrquartz"
    saved = client.post("/api/entries", json={"body": f"I want to die. {unique}", "mood": 1})
    assert saved.status_code == 200
    body = saved.json()
    assert body["reflection"] is None
    assert body["safety"]["stored"] is True
    assert "<HELPLINE_PLACEHOLDER>" in saved.text
    assert "diagnosis of" not in body["safety"]["message"].lower()
    assert unique not in body["safety"]["message"]
    assert body["entry"]["analysis_status"] == "held"

    listed = client.get("/api/entries").json()["entries"]
    held = next(entry for entry in listed if entry["id"] == body["entry"]["id"])
    assert held["safety_hold"] is True
    assert held["reflection"] is None
    found = client.get("/api/search", params={"q": unique}).json()
    assert found["results"] == []

    client.post("/api/session", json={"user_id": "jonah"})
    assert client.get(f"/api/entries/{body['entry']['id']}").status_code == 404


def test_ordinary_rough_day_still_gets_a_reflection(client):
    saved = client.post(
        "/api/entries",
        json={"body": "This deadline is killing me and I ate at my desk.", "mood": 2},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["safety"] is None
    assert body["reflection"]["mood_label"] == "low"
    assert body["reflection"]["source"] == "mock"
    assert "not medical advice" in body["reflection"]["disclaimer"].lower()


def test_live_reflection_cannot_invent_a_citation(client):
    def transport(_messages):
        return json.dumps(
            {
                "summary": "The train stalled and lunch was at the desk again.",
                "themes": ["desk"],
                "pattern_note": "An earlier note sat in the same place.",
                "gentle_prompt": "Where could lunch happen tomorrow that is not the desk?",
                "citation_ids": ["not-a-real-id", "maya-d1"],
            }
        )

    client.app.state.llm_transport = transport
    saved = client.post(
        "/api/entries",
        json={"body": "The train stalled again and I ate lunch at my desk.", "mood": 2},
    )
    reflection = saved.json()["reflection"]
    assert reflection["source"] == "llm"
    assert all(item["entry_id"] != "not-a-real-id" for item in reflection["citations"])
    if reflection["citations"]:
        assert reflection["citations"][0]["entry_id"] == "maya-d1"
        assert "train" in reflection["citations"][0]["excerpt"].lower()


def test_clinical_model_output_falls_back_offline(client):
    def transport(_messages):
        return json.dumps(
            {
                "summary": "This is a diagnosis of depression.",
                "themes": ["desk"],
                "pattern_note": "Nothing earlier is close enough to cite.",
                "gentle_prompt": "What did you notice?",
                "citation_ids": [],
            }
        )

    client.app.state.llm_transport = transport
    saved = client.post("/api/entries", json={"body": "I ate lunch at my desk again.", "mood": 3})
    reflection = saved.json()["reflection"]
    assert reflection["fallback"] is True
    assert reflection["source"] == "mock"
    assert "diagnosis" not in reflection["summary"].lower()


def test_habit_model_cannot_change_the_counts(client):
    board = client.get("/api/habits").json()

    def honest(_messages):
        return json.dumps(
            {
                "observation": "The counts are already on the card.",
                "one_small_step": "Tomorrow, only this: Lunch away from the desk.",
                "habits": [
                    {
                        "habit_id": habit["habit_id"],
                        "name": habit["name"],
                        "done_days": habit["done_days"],
                        "window_days": habit["window_days"],
                        "streak": habit["streak"],
                    }
                    for habit in board["habits"]
                ],
            }
        )

    client.app.state.llm_transport = honest
    live = client.get("/api/habits").json()
    assert live["source"] == "llm"
    assert live["observation"] == "The counts are already on the card."
    assert [habit["done_days"] for habit in live["habits"]] == [habit["done_days"] for habit in board["habits"]]

    def dishonest(_messages):
        return json.dumps(
            {
                "observation": "You completed every habit, 7/7.",
                "one_small_step": "Nothing to change.",
                "habits": [
                    {
                        "habit_id": "maya-walk",
                        "name": "Morning walk",
                        "done_days": 7,
                        "window_days": 7,
                        "streak": 7,
                    }
                ],
            }
        )

    client.app.state.llm_transport = dishonest
    kept = client.get("/api/habits").json()
    assert kept["fallback"] is True
    assert kept["source"] == "mock"
    walk = next(habit for habit in kept["habits"] if habit["habit_id"] == "maya-walk")
    walk_done = done_dates("maya", "walk", date.today())
    window = {date.today() - timedelta(days=offset) for offset in range(7)}
    assert walk["done_days"] == len(walk_done & window)
    assert "7/7" not in kept["observation"]


def test_preview_does_not_echo_the_trigger_or_store_a_note(client):
    before = len(client.get("/api/entries").json()["entries"])
    preview = client.post("/api/safety/preview")
    assert preview.status_code == 200
    text = preview.text.lower()
    assert "i want to die" not in text
    assert preview.json()["stored"] is False
    assert "<helpline_placeholder>" in text
    after = len(client.get("/api/entries").json()["entries"])
    assert after == before
