import pytest

KCS = {"feedback_topology": {"kc_id": "feedback_topology", "name": "反馈组态判断",
                             "prerequisites": [], "exam_weight": 0.9,
                             "chapter_id": None, "source_ids": [], "explained": False}}

PASSED = {"generator": {"status": "passed"},
          "independent_solver": {"status": "passed", "answer_match": True},
          "adversarial_review": {"status": "passed", "issues": []},
          "mechanical_validator": {"type": "sympy", "status": "passed"}}


def _syn(**over):
    q = {"question_id": "syn_q_018", "kc_ids": ["feedback_topology"],
         "source_type": "synthetic", "transfer_level": "T2",
         "stem": "反向推断反馈类型", "answer": "B",
         "changed_dimensions": ["question_direction", "information_structure"],
         "preserved_dimensions": ["core_kc", "target_capability", "cognitive_trap"],
         "derived_from": ["kc:feedback_topology", "error:err_001", "question:past_2023_q17"],
         "validation": dict(PASSED)}
    q.update(over)
    return q


def test_real_question_needs_no_validation_block():
    from studylib.validation import validate_candidate
    q = {"question_id": "past_2023_q17", "kc_ids": ["feedback_topology"],
         "source_type": "past_exam", "transfer_level": "T0",
         "stem": "判断反馈组态", "answer": "A"}
    assert validate_candidate(KCS, q) == []


def test_synthetic_requires_gates():
    from studylib.validation import validate_candidate
    assert validate_candidate(KCS, _syn(validation=None))
    bad_solver = dict(PASSED, independent_solver={"status": "passed", "answer_match": False})
    issues = validate_candidate(KCS, _syn(validation=bad_solver))
    assert any("solver" in i.lower() or "答案" in i for i in issues)


def test_number_swap_cannot_claim_t2():
    from studylib.validation import validate_candidate
    issues = validate_candidate(KCS, _syn(changed_dimensions=["surface_context"]))
    assert any("surface_context" in i or "换数字" in i for i in issues)


def test_unknown_kc_rejected():
    from studylib.validation import validate_candidate
    issues = validate_candidate(KCS, _syn(kc_ids=["ghost_kc"]))
    assert any("ghost_kc" in i for i in issues)


def test_register_question_appends_correct_event(course):
    from studylib.errors import ValidationFailed
    from studylib.events import append_event, new_event, read_events
    from studylib.validation import register_question
    append_event(course, new_event("analog-electronics", "kc_created",
                                   {"kc_id": "feedback_topology", "name": "反馈组态判断"}))
    ev = register_question(course, _syn(), as_transfer_test=True)
    assert ev["event_type"] == "transfer_test_created"
    assert read_events(course)[-1]["payload"]["question_id"] == "syn_q_018"
    with pytest.raises(ValidationFailed):
        register_question(course, _syn(validation=None))
