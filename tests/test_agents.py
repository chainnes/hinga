import pytest
from pydantic import ValidationError

from hinga.agents import RetrievedNote, reflection_from_draft
from hinga.llm import parse_json_object
from hinga.safety import is_crisis
from hinga.schemas import ReflectionDraft, reject_clinical_claims


@pytest.mark.parametrize(
    "text",
    [
        "I want to die",
        "I have been suicidal this week",
        "I don't want to live",
        "I keep thinking about self-harm",
    ],
)
def test_crisis_phrases_hold(text):
    assert is_crisis(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "This deadline is killing me",
        "I felt awful after the meeting and cried on the train",
        "I slept badly and ate lunch at my desk",
        "",
    ],
)
def test_ordinary_distress_is_not_a_hold(text):
    assert is_crisis(text) is False


def test_clinical_claims_are_rejected():
    with pytest.raises(ValueError):
        reject_clinical_claims("This is a diagnosis of depression.")
    with pytest.raises(ValidationError):
        ReflectionDraft(
            summary="You have depression and this caused it.",
            pattern_note="Nothing earlier is close enough to cite.",
            gentle_prompt="What did you notice?",
            citation_ids=[],
        )


def test_json_fences_are_stripped():
    data = parse_json_object('```json\n{"summary": "You wrote about the train."}\n```')
    assert data["summary"].startswith("You wrote")


def test_unknown_citation_ids_are_dropped():
    note = RetrievedNote(
        entry_id="maya-d1",
        date_label="14 Nov",
        excerpt="I slept badly, then the train stalled.",
        overlap=0.55,
        themes=["sleep"],
    )
    draft = ReflectionDraft(
        summary="The train stalled and lunch was at the desk.",
        themes=["commute"],
        pattern_note="A note from 14 Nov sat in the same place.",
        gentle_prompt="Where did you eat, exactly?",
        citation_ids=["not-a-real-id", "maya-d1"],
    )
    reflection = reflection_from_draft(draft, 2, [note], source="llm", fallback=False)
    assert [item.entry_id for item in reflection.citations] == ["maya-d1"]
    assert reflection.citations[0].excerpt == note.excerpt
    assert reflection.mood_label == "low"
    assert "not medical advice" in reflection.disclaimer.lower()
