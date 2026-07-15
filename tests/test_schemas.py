import pytest
from pydantic import ValidationError


def test_vocab_sizes():
    from studylib import schemas as S
    assert len(S.EVENT_TYPES) == 30
    assert len(S.ERROR_TYPES) == 14
    assert len(S.CHANGED_DIMENSIONS) == 8
    assert len(S.SOURCE_TYPES) == 10
    assert len(S.CARD_TYPES) == 5
    assert S.TRANSFER_LEVELS == ("T0", "T1", "T2", "T3", "T4")
    assert S.TRANSFER_KEY["T2"] == "T2_structural"


def test_event_roundtrip_and_defaults():
    from studylib.schemas import Event
    ev = Event(
        event_id="evt_x", timestamp="2026-07-15T14:32:18+08:00",
        event_type="question_attempted", course_id="c1",
        payload={"question_id": "q1", "correct": False},
    )
    d = ev.model_dump()
    assert d["schema_version"] == "2.0"
    assert d["session_id"] == "session_adhoc"
    assert d["actor"] == "student"


def test_event_rejects_unknown_type():
    from studylib.schemas import Event
    with pytest.raises(ValidationError):
        Event(event_id="e", timestamp="t", event_type="nope", course_id="c")


def test_question_validation_vocab():
    from studylib.schemas import Question
    q = Question(
        question_id="syn_q_018", kc_ids=["feedback_topology"], source_type="synthetic",
        transfer_level="T2", stem="...", answer="B",
        changed_dimensions=["question_direction", "information_structure"],
        preserved_dimensions=["core_kc", "target_capability", "cognitive_trap"],
        derived_from=["kc:feedback_topology", "error:err_001", "question:past_2023_q17"],
    )
    assert q.transfer_level == "T2"
    with pytest.raises(ValidationError):
        Question(question_id="q", kc_ids=["k"], source_type="not_a_source",
                 stem="s", answer="a")
    with pytest.raises(ValidationError):
        Question(question_id="q", kc_ids=["k"], source_type="synthetic",
                 stem="s", answer="a", changed_dimensions=["magic"])
