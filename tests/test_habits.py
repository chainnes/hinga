from datetime import date, timedelta

import pytest

from hinga.habits import (
    adapt_intention,
    build_stat,
    current_streak,
    guilt_free_reframe,
    one_small_step,
    sleep_miss_count,
    weekly_observation,
)
from hinga.schemas import HabitStat


def test_streak_counts_back_from_yesterday_when_today_is_open():
    today = date(2026, 11, 15)
    done = {today - timedelta(days=n) for n in (1, 2, 4)}
    assert current_streak(done, today) == 2
    assert current_streak(done | {today}, today) == 3
    assert current_streak(set(), today) == 0


def test_sleep_miss_needs_two_days_and_ignores_today():
    today = date(2026, 11, 15)
    done = {today - timedelta(days=2)}
    stat = build_stat(
        habit_id="lights",
        name="Lights out by 11",
        intention="Phone in the other room.",
        done_dates=done,
        today=today,
        window=7,
    )
    notes = {
        today - timedelta(days=1): ["I was awake until two."],
        today - timedelta(days=3): ["Slept badly and left the lights on."],
        today: ["Awake right now."],
    }
    assert sleep_miss_count(stat, notes) == 2
    assert "Lights out by 11" in one_small_step([stat])


def test_step_picks_the_least_kept_habit():
    today = date(2026, 11, 15)
    walk = build_stat(
        habit_id="walk",
        name="Morning walk",
        intention="Ten minutes outside.",
        done_dates={today - timedelta(days=n) for n in range(1, 6)},
        today=today,
    )
    lunch = build_stat(
        habit_id="lunch",
        name="Lunch away from the desk",
        intention="Eat somewhere that is not the keyboard.",
        done_dates={today - timedelta(days=2)},
        today=today,
    )
    step = one_small_step([walk, lunch])
    assert "Lunch away from the desk" in step
    assert isinstance(walk, HabitStat)


def test_repeated_misses_shrink_the_wording_without_a_scolding():
    today = date(2026, 11, 15)
    done = {today - timedelta(days=5), today - timedelta(days=6)}
    smaller, shrunk = adapt_intention("Ten minutes outside.", "Two minutes at the door.", done, today)
    assert shrunk is True
    assert smaller == "Two minutes at the door."
    kept, still = adapt_intention("Ten minutes outside.", "Two minutes at the door.", {today - timedelta(days=n) for n in range(1, 7)}, today)
    assert still is False
    assert kept.startswith("Ten minutes")
    line = guilt_free_reframe("Lights out by 11", done, today)
    assert line is not None
    lowered = line.lower()
    for banned in ("guilt", "failed", "lazy", "should", "disappointed"):
        assert banned not in lowered
    assert guilt_free_reframe("Morning walk", {today - timedelta(days=1)}, today) is None


def test_weekly_note_is_an_observation():
    note = weekly_observation([2, 2, 3], [4, 5, 4], ["sleep", "sleep", "work"])
    assert "lower" in note
    assert "sleep" in note
    assert "Not a cause." in note
    assert "diagnos" not in note.lower()
