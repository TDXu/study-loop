import pytest


def _ev(etype, payload):
    from studylib.events import new_event
    return new_event("c1", etype, payload)


def test_build_kcs_create_update_explained():
    from studylib.registry import build_kcs
    events = [
        _ev("kc_created", {"kc_id": "k1", "name": "反馈组态判断", "chapter_id": "ch6",
                           "prerequisites": [], "exam_weight": 0.9}),
        _ev("kc_created", {"kc_id": "k2", "name": "深度负反馈", "chapter_id": "ch6",
                           "prerequisites": ["k1"]}),
        _ev("kc_updated", {"kc_id": "k1", "update": "explained"}),
        _ev("kc_updated", {"kc_id": "k2", "exam_weight": 0.8}),
    ]
    kcs = build_kcs(events)
    assert kcs["k1"]["explained"] is True
    assert kcs["k1"]["exam_weight"] == 0.9
    assert kcs["k2"]["prerequisites"] == ["k1"]
    assert kcs["k2"]["exam_weight"] == 0.8
    assert kcs["k2"]["explained"] is False


def test_kc_updated_unknown_raises():
    from studylib.errors import UnknownKC
    from studylib.registry import build_kcs
    with pytest.raises(UnknownKC):
        build_kcs([_ev("kc_updated", {"kc_id": "ghost", "update": "explained"})])


def test_build_questions_from_both_event_types():
    from studylib.registry import build_questions
    q1 = {"question_id": "past_2023_q17", "kc_ids": ["k1"], "source_type": "past_exam",
          "transfer_level": "T0", "stem": "s", "answer": "A"}
    q2 = {"question_id": "syn_q_018", "kc_ids": ["k1"], "source_type": "synthetic",
          "transfer_level": "T2", "stem": "s2", "answer": "B",
          "retest_of_error_id": "err_001"}
    qs = build_questions([_ev("question_registered", q1), _ev("transfer_test_created", q2)])
    assert set(qs) == {"past_2023_q17", "syn_q_018"}
    assert qs["syn_q_018"]["transfer_level"] == "T2"


def test_build_sources():
    from studylib.registry import build_sources
    src = {"source_id": "src_012", "source_type": "lecture_slide",
           "file": "materials/slides/chapter6.pdf", "sha256": "sha256:x", "pages": [12, 13]}
    assert build_sources([_ev("source_registered", src)]) == [src]
