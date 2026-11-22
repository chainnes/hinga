"""Habit arithmetic. The model may phrase a sentence. It does not own the counts."""

from __future__ import annotations

from datetime import date, timedelta

from hinga.schemas import HabitDay, HabitStat
from hinga.textutil import detect_themes


def window_dates(today: date, days: int = 7) -> list[date]:
    start = today - timedelta(days=days - 1)
    return [start + timedelta(days=offset) for offset in range(days)]


def current_streak(done_dates: set[date], today: date) -> int:
    """Count back from today, or from yesterday if today is still open."""
    cursor = today if today in done_dates else today - timedelta(days=1)
    streak = 0
    while cursor in done_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def build_stat(
    *,
    habit_id: str,
    name: str,
    intention: str,
    done_dates: set[date],
    today: date,
    window: int = 7,
) -> HabitStat:
    days = window_dates(today, window)
    done_in_window = [day for day in days if day in done_dates]
    return HabitStat(
        habit_id=habit_id,
        name=name,
        intention=intention,
        done_days=len(done_in_window),
        window_days=window,
        streak=current_streak(done_dates, today),
        days=[
            HabitDay(
                date=day.isoformat(),
                label=day.strftime("%a"),
                done=day in done_dates,
                is_today=day == today,
            )
            for day in days
        ],
    )


def sleep_miss_count(stat: HabitStat, entry_texts_by_date: dict[date, list[str]]) -> int:
    """Days in the window where this habit was missed and a note mentions sleep."""
    count = 0
    for day in stat.days:
        if day.done or day.is_today:
            continue
        moment = date.fromisoformat(day.date)
        texts = entry_texts_by_date.get(moment, [])
        if any("sleep" in detect_themes(text) for text in texts):
            count += 1
    return count


def strongest_sleep_note(stats: list[HabitStat], entry_texts_by_date: dict[date, list[str]]) -> tuple[str, int] | None:
    best: tuple[str, int] | None = None
    for stat in stats:
        count = sleep_miss_count(stat, entry_texts_by_date)
        if count < 2:
            continue
        if best is None or count > best[1]:
            best = (stat.name, count)
    return best


def build_observation(stats: list[HabitStat], sleep_note: tuple[str, int] | None) -> str:
    if not stats:
        return "No habits on this desk yet."
    parts = [
        f"{stat.name} {stat.done_days}/{stat.window_days}, streak {stat.streak}"
        for stat in stats
    ]
    sentence = "Over the last 7 days: " + "; ".join(parts) + "."
    if sleep_note:
        name, count = sleep_note
        sentence += (
            f" On {count} days when {name} was missed, that day's note also mentioned sleep."
            " Worth noticing. Not a cause."
        )
    return sentence


def one_small_step(stats: list[HabitStat]) -> str:
    if not stats:
        return "Add one habit small enough to do on a bad day."
    chosen = sorted(stats, key=lambda stat: (stat.done_days, stat.streak, stat.name))[0]
    if chosen.done_days >= chosen.window_days:
        return f"Keep the smallest one. Tomorrow, {chosen.name} again. {chosen.intention}"
    return f"Tomorrow, only this: {chosen.name}. {chosen.intention}"


SHRINK_AFTER_MISSES = 4


def past_days(today: date, window: int = 7) -> list[date]:
    """The window, not counting today. Today is still open."""
    return [day for day in window_dates(today, window) if day != today]


def miss_count(done_dates: set[date], today: date) -> int:
    return sum(1 for day in past_days(today) if day not in done_dates)


def adapt_intention(full: str, small: str, done_dates: set[date], today: date) -> tuple[str, bool]:
    """Shrink the wording after repeated misses. The record of the misses stays."""
    if small.strip() and miss_count(done_dates, today) >= SHRINK_AFTER_MISSES:
        return small, True
    return full, False


def guilt_free_reframe(name: str, done_dates: set[date], today: date) -> str | None:
    yesterday = today - timedelta(days=1)
    if yesterday in done_dates:
        return None
    return (
        f"Yesterday {name} didn't happen. That is a miss, not a verdict. "
        "The streak can start again today, and nothing is owed."
    )


def weekly_observation(this_week: list[int], last_week: list[int], themes: list[str]) -> str:
    """Compare two weeks of check-in marks. The sentence does not name a cause."""
    if not this_week:
        return "No notes in the last 7 days to compare."
    average = sum(this_week) / len(this_week)
    if last_week:
        previous = sum(last_week) / len(last_week)
        if average <= previous - 0.4:
            trend = "The marks this week sit lower than the week before."
        elif average >= previous + 0.4:
            trend = "The marks this week sit higher than the week before."
        else:
            trend = "The marks this week sit near the week before."
    else:
        trend = "There isn't a previous week on this desk to compare."
    theme_line = ""
    if themes:
        top = max(set(themes), key=themes.count)
        theme_line = f" The theme that shows up most is {top}."
    return trend + theme_line + " Worth noticing. Not a cause."


def facts_match(draft_habits: list, stats: list[HabitStat]) -> bool:
    by_id = {stat.habit_id: stat for stat in stats}
    if len(draft_habits) != len(stats):
        return False
    for draft in draft_habits:
        source = by_id.get(draft.habit_id)
        if source is None:
            return False
        if (draft.done_days, draft.window_days, draft.streak, draft.name) != (
            source.done_days,
            source.window_days,
            source.streak,
            source.name,
        ):
            return False
    return True
