"""Timed practices. The script is a file in this package. Mood only picks which one."""

from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).resolve().parent

# mood -> (file, display name, minutes). Every length is between 1 and 5.
_PLAN = {
    1: ("grounding_54321.md", "5-4-3-2-1 grounding", 2),
    2: ("grounding_54321.md", "5-4-3-2-1 grounding", 3),
    3: ("box_breathing.md", "Box breathing", 3),
    4: ("box_breathing.md", "Box breathing", 4),
    5: ("body_scan.md", "Body scan", 5),
}


def exercise_for_mood(mood: int) -> dict:
    filename, name, minutes = _PLAN[mood]
    script = (_DIR / filename).read_text(encoding="utf-8").strip()
    if not 1 <= minutes <= 5:
        raise RuntimeError("mindfulness script is outside 1–5 minutes")
    return {
        "name": name,
        "minutes": minutes,
        "script": script,
        "script_file": f"hinga/mindfulness/{filename}",
        "adapted_to": mood,
    }
