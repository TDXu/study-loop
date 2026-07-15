import json


def _seed_minimal_flow(root):
    """kc + 真题 + 高置信度错误 + 归因，构成最小派生输入。"""
    from studylib.events import append_event, new_event
    cid = "analog-electronics"
    append_event(root, new_event(cid, "kc_created",
                                 {"kc_id": "feedback_topology", "name": "反馈组态判断",
                                  "chapter_id": "chapter_06", "exam_weight": 0.9}))
    append_event(root, new_event(cid, "question_registered",
                                 {"question_id": "past_2023_q17", "kc_ids": ["feedback_topology"],
                                  "source_type": "past_exam", "transfer_level": "T0",
                                  "stem": "判断反馈组态", "answer": "A"}))
    append_event(root, new_event(cid, "confidence_recorded",
                                 {"question_id": "past_2023_q17", "confidence_before": 0.9}))
    append_event(root, new_event(cid, "question_attempted",
                                 {"question_id": "past_2023_q17", "answer": "B", "correct": False,
                                  "confidence_before": 0.9, "hint_level": 0}))
    append_event(root, new_event(cid, "misconception_identified",
                                 {"error_id": "err_001", "kc_ids": ["feedback_topology"],
                                  "origin_question_id": "past_2023_q17",
                                  "wrong_assumption": "输出端有反馈连接即电压反馈",
                                  "missing_premise": "必须检查取样方式",
                                  "error_type": "concept_misconception",
                                  "trigger_conditions": ["复杂电路图"],
                                  "confidence_before": 0.9, "attribution_confidence": 0.82}))


def test_derive_writes_all_artifacts(course):
    from studylib.derive import derive
    _seed_minimal_flow(course)
    result = derive(course)
    study = course / ".study"
    for f in ["state.json", "kc.json", "evidence.jsonl", "errors.jsonl",
              "cards.jsonl", "questions.jsonl", "sources.jsonl", "dashboard.md"]:
        assert (study / f).exists(), f

    state = json.loads((study / "state.json").read_text(encoding="utf-8"))
    assert state["schema_version"] == "2.0"
    assert state["course"]["id"] == "analog-electronics"
    assert state["exam"]["date"] == "2026-07-25"
    assert state["counts"]["weak"] == 1
    assert state["active_misconceptions"] == 1
    nbs = state["next_best_step"]
    assert nbs["action"] == "repair"
    assert nbs["kc_id"] == "feedback_topology"
    assert nbs["reasons"]

    kc = json.loads((study / "kc.json").read_text(encoding="utf-8"))
    assert kc["feedback_topology"]["teaching_state"] == "weak"
    assert result["state"]["next_best_step"]["action"] == "repair"


def test_dashboard_contains_recommendation(course):
    from studylib.derive import derive
    _seed_minimal_flow(course)
    derive(course)
    text = (course / ".study" / "dashboard.md").read_text(encoding="utf-8")
    assert "今日建议" in text
    assert "反馈组态判断" in text
    assert "为什么" in text


def test_rebuild_dry_run_reports_no_diff_after_derive(course):
    from studylib.derive import derive, rebuild
    _seed_minimal_flow(course)
    derive(course)
    diff = rebuild(course, dry_run=True)
    assert diff["changed_kc_states"] == {}


def test_rebuild_writes_event_and_state(course):
    from studylib.derive import derive, rebuild
    from studylib.events import read_events
    _seed_minimal_flow(course)
    derive(course)
    rebuild(course)
    assert any(e["event_type"] == "state_rebuilt" for e in read_events(course))
