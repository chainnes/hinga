from hinga.config import Settings
from hinga.copy import FIXED_SAFETY_RESPONSE
from hinga.graph import invoke_desk
from hinga.mindfulness import exercise_for_mood
from hinga.safety import CRISIS_PHRASES, is_crisis


def _memory(_text: str) -> dict:
    return {
        "profile": {"values": "Sleep as a boundary.", "goals": "Lights out.", "tone": "Plain."},
        "retrieved": [],
        "habits": [],
        "week_note": "No notes in the last 7 days to compare.",
    }


def test_twenty_crisis_phrases_all_hit_the_fixed_response():
    assert len(CRISIS_PHRASES) >= 20

    def memory_must_not_run(_text: str) -> dict:
        raise AssertionError("memory ran after a crisis note")

    def model_must_not_run(_messages):
        raise AssertionError("a model ran after a crisis note")

    for phrase in CRISIS_PHRASES:
        assert is_crisis(phrase)
        result = invoke_desk(
            text=phrase,
            mood=1,
            route="journal",
            load_memory=memory_must_not_run,
            settings=Settings(llm_provider="openai", llm_api_key="present"),
            transport=model_must_not_run,
        )
        assert result["route"] == "safety_guard"
        assert result["safety"]["message"] == FIXED_SAFETY_RESPONSE
        assert result["reflection"] is None
        assert result["analysis"] is None
        assert "diagnosis of" not in result["safety"]["message"].lower()


def test_ordinary_stress_is_not_a_crisis():
    for phrase in (
        "This deadline is killing me",
        "I felt awful and cried on the train",
        "The meeting killed my energy",
        "I slept badly and ate at my desk",
    ):
        assert is_crisis(phrase) is False


def test_clear_note_can_reach_a_branch_with_the_model_unused():
    result = invoke_desk(
        text="",
        mood=1,
        route="mindfulness",
        load_memory=_memory,
        settings=Settings(),
        transport=None,
    )
    assert result["route"] == "mindfulness"
    assert result["exercise"]["minutes"] == 2
    assert "five things you can see" in result["exercise"]["script"].lower()


def test_scripts_stay_between_one_and_five_minutes():
    for mood in range(1, 6):
        exercise = exercise_for_mood(mood)
        assert 1 <= exercise["minutes"] <= 5
        assert exercise["script"]
    assert exercise_for_mood(5)["name"] == "Body scan"
    assert exercise_for_mood(3)["name"] == "Box breathing"
