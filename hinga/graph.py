"""safety_guard, then memory, then one branch. Crisis never reaches a model."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph


class DeskState(TypedDict, total=False):
    text: str
    mood: int
    requested_route: str
    held: bool
    memory: dict
    result: dict

from hinga.agents import RetrievedNote, analyze, reflect
from hinga.config import Settings
from hinga.llm import Transport
from hinga.mindfulness import exercise_for_mood
from hinga.safety import is_crisis, safety_payload

BRANCHES = ("mindfulness", "journal", "habit", "insights")
MemoryLoader = Callable[[str], dict]


def _route(state: dict) -> str:
    route = state.get("requested_route") or "journal"
    if route not in BRANCHES:
        return "journal"
    return route


def compile_desk(load_memory: MemoryLoader, settings: Settings, transport: Transport | None = None):
    def safety_guard(state: dict) -> dict:
        if is_crisis(state.get("text") or ""):
            return {
                "held": True,
                "result": {
                    "route": "safety_guard",
                    "safety": safety_payload(stored=True).model_dump(),
                    "reflection": None,
                    "analysis": None,
                    "analysis_status": "held",
                    "exercise": None,
                },
            }
        return {"held": False}

    def after_safety(state: dict) -> str:
        return "end" if state.get("held") else "memory"

    def memory(state: dict) -> dict:
        return {"memory": load_memory(state.get("text") or "")}

    def mindfulness(state: dict) -> dict:
        mood = int(state.get("mood") or 3)
        exercise = exercise_for_mood(mood)
        profile = (state.get("memory") or {}).get("profile") or {}
        tone = (profile.get("tone") or "plain").rstrip(".")
        exercise["note"] = f"Tone on this desk: {tone}."
        return {"result": {"route": "mindfulness", "safety": None, "exercise": exercise, "reflection": None}}

    def journal(state: dict) -> dict:
        text = state.get("text") or ""
        mood = int(state.get("mood") or 3)
        memory = state.get("memory") or {}
        retrieved = [RetrievedNote(**item) for item in memory.get("retrieved") or []]
        analysis, status = analyze(text, mood, settings, transport=transport)
        reflection = None
        if status != "held":
            reflection = reflect(text, mood, retrieved, settings, transport=transport)
            values = (memory.get("profile") or {}).get("values")
            if values and reflection is not None:
                prompt = reflection.gentle_prompt
                extra = f" Your values on this desk: {values}"
                if len(prompt) + len(extra) <= 280:
                    reflection = reflection.model_copy(update={"gentle_prompt": prompt + extra})
        return {
            "result": {
                "route": "journal",
                "safety": None,
                "exercise": None,
                "reflection": None if reflection is None else reflection.model_dump(),
                "analysis": None if analysis is None else analysis.model_dump(),
                "analysis_status": status,
            }
        }

    def habit(state: dict) -> dict:
        memory = state.get("memory") or {}
        profile = memory.get("profile") or {}
        stats = memory.get("habits") or []
        reframes = [item.get("reframe") for item in stats if item.get("reframe")]
        shrunk = [item["name"] for item in stats if item.get("shrunk")]
        line = reframes[0] if reframes else "Nothing missed yesterday. Keep the same size today."
        if shrunk:
            line = f"{line} Smaller wording now: {', '.join(shrunk)}."
        goal = profile.get("goals") or ""
        if goal:
            line = f"{line} The goal on this desk: {goal}"
        return {
            "result": {
                "route": "habit",
                "safety": None,
                "exercise": None,
                "reflection": None,
                "habit_note": line,
                "analysis": None,
                "analysis_status": "analyzed" if state.get("text") else None,
            }
        }

    def insights(state: dict) -> dict:
        memory = state.get("memory") or {}
        return {
            "result": {
                "route": "insights",
                "safety": None,
                "exercise": None,
                "reflection": None,
                "week_note": memory.get("week_note") or "No notes in the last 7 days to compare.",
            }
        }

    graph = StateGraph(DeskState)
    graph.add_node("safety_guard", safety_guard)
    graph.add_node("memory", memory)
    graph.add_node("mindfulness", mindfulness)
    graph.add_node("journal", journal)
    graph.add_node("habit", habit)
    graph.add_node("insights", insights)
    graph.add_edge(START, "safety_guard")
    graph.add_conditional_edges("safety_guard", after_safety, {"memory": "memory", "end": END})
    graph.add_conditional_edges("memory", _route, {name: name for name in BRANCHES})
    for name in BRANCHES:
        graph.add_edge(name, END)
    return graph.compile()


def invoke_desk(
    *,
    text: str,
    mood: int | None,
    route: str,
    load_memory: MemoryLoader,
    settings: Settings,
    transport: Transport | None = None,
) -> dict[str, Any]:
    graph = compile_desk(load_memory, settings, transport)
    state = graph.invoke(
        {
            "text": text,
            "mood": mood,
            "requested_route": route,
            "held": False,
        }
    )
    return state.get("result") or {}
