"""spec §42.2 场景 A：完整错题闭环（+场景 C 提示依赖断言）。"""
import json

CID = "analog-electronics"

PASSED_GATES = {"generator": {"status": "passed"},
                "independent_solver": {"status": "passed", "answer_match": True},
                "adversarial_review": {"status": "passed", "issues": []}}


def _ev(root, etype, payload):
    from studylib.events import append_event, new_event
    return append_event(root, new_event(CID, etype, payload))


def test_full_misconception_loop(course):
    from studylib.derive import derive
    from studylib.fsrs_store import new_card_payload
    from studylib.validation import register_question

    # 注册 KC（带前置关系）与真题
    _ev(course, "kc_created", {"kc_id": "feedback_topology", "name": "反馈组态判断",
                               "chapter_id": "chapter_06", "exam_weight": 0.9})
    _ev(course, "kc_created", {"kc_id": "deep_negative_feedback", "name": "深度负反馈",
                               "chapter_id": "chapter_06", "exam_weight": 0.8,
                               "prerequisites": ["feedback_topology"]})
    register_question(course, {
        "question_id": "past_2023_q17", "kc_ids": ["feedback_topology"],
        "source_type": "past_exam", "transfer_level": "T0",
        "stem": "判断该电路的反馈组态", "answer": "A"})

    # 高置信度答错 → 三步归因 → 修复
    _ev(course, "confidence_recorded", {"question_id": "past_2023_q17", "confidence_before": 0.9})
    _ev(course, "question_attempted", {"question_id": "past_2023_q17", "answer": "B",
                                       "correct": False, "confidence_before": 0.9, "hint_level": 0})
    _ev(course, "misconception_identified", {
        "error_id": "err_001", "kc_ids": ["feedback_topology"],
        "origin_question_id": "past_2023_q17",
        "wrong_assumption": "输出端存在反馈连接即可视为电压反馈",
        "missing_premise": "必须检查反馈网络对输出端的取样方式",
        "error_type": "concept_misconception",
        "trigger_conditions": ["复杂电路图"],
        "confidence_before": 0.9, "attribution_confidence": 0.82})

    mid = derive(course)
    assert mid["state"]["next_best_step"]["action"] == "repair"
    assert mid["kc"]["feedback_topology"]["teaching_state"] == "weak"
    assert mid["kc"]["deep_negative_feedback"]["teaching_state"] == "blocked"

    _ev(course, "repair_started", {"error_id": "err_001", "repair_id": "repair_012"})
    _ev(course, "repair_completed", {"error_id": "err_001"})

    # 原题二刷正确
    _ev(course, "question_attempted", {"question_id": "past_2023_q17", "correct": True,
                                       "confidence_before": 0.75, "hint_level": 0,
                                       "retest_of_error_id": "err_001"})

    # T0 检查点：单次正确不足以解决错因
    t0_check = derive(course)
    assert t0_check["misconceptions"]["err_001"]["repair_status"] == "retest_pending"

    # T1 迁移题（过闸门）→ 正确；T2 → 错误
    register_question(course, {
        "question_id": "syn_t1_001", "kc_ids": ["feedback_topology"],
        "source_type": "synthetic", "transfer_level": "T1",
        "stem": "换数值的同结构题", "answer": "C",
        "changed_dimensions": ["surface_context"],
        "preserved_dimensions": ["core_kc", "target_capability", "cognitive_trap"],
        "derived_from": ["kc:feedback_topology", "error:err_001", "question:past_2023_q17"],
        "validation": dict(PASSED_GATES)}, as_transfer_test=True)
    register_question(course, {
        "question_id": "syn_t2_001", "kc_ids": ["feedback_topology"],
        "source_type": "synthetic", "transfer_level": "T2",
        "stem": "反向推断：已知组态求电路特征", "answer": "D",
        "changed_dimensions": ["question_direction", "information_structure"],
        "preserved_dimensions": ["core_kc", "target_capability", "cognitive_trap"],
        "derived_from": ["kc:feedback_topology", "error:err_001", "question:past_2023_q17"],
        "validation": dict(PASSED_GATES)}, as_transfer_test=True)

    _ev(course, "transfer_test_attempted", {"question_id": "syn_t1_001", "correct": True,
                                            "confidence_before": 0.75, "hint_level": 0,
                                            "retest_of_error_id": "err_001"})
    _ev(course, "transfer_test_attempted", {"question_id": "syn_t2_001", "correct": False,
                                            "confidence_before": 0.75, "hint_level": 0,
                                            "retest_of_error_id": "err_001"})

    # 原题进 FSRS（原题必须可调度）
    _ev(course, "fsrs_card_created",
        new_card_payload("original_question", ["feedback_topology"], "past_2023_q17"))

    final = derive(course)
    kc = final["kc"]["feedback_topology"]
    err = final["misconceptions"]["err_001"]
    state = final["state"]

    # T2 失败 → 错因回到 active、KC weak、推荐继续修复（§42.2 场景 A 结尾）
    assert err["repair_status"] == "active"
    assert "syn_t2_001" in err["transfer_failures"]
    # 三步归因内容存储检验
    assert err["wrong_assumption"] == "输出端存在反馈连接即可视为电压反馈"
    assert err["missing_premise"] == "必须检查反馈网络对输出端的取样方式"
    assert err["attribution_confidence"] == 0.82
    assert kc["teaching_state"] == "weak"
    assert kc["transfer"]["T1_near"] == 1.0
    assert kc["transfer"]["T2_structural"] == 0.0
    assert state["next_best_step"]["action"] == "repair"
    assert state["next_best_step"]["kc_id"] == "feedback_topology"
    assert any("T2" in r or "迁移" in r for r in state["next_best_step"]["reasons"])
    assert kc["retention"]["fsrs_card_ids"], "原题必须有 FSRS 卡"

    # 派生文件与事件真相一致：errors.jsonl 里就是这条错因
    errors_rows = [json.loads(line) for line in
                   (course / ".study" / "errors.jsonl").read_text(encoding="utf-8").splitlines()]
    assert errors_rows[0]["error_id"] == "err_001"


def test_scenario_c_hint_dependence(course):
    """L4 后答对 → 不允许 checked；随后独立答对 → checked。"""
    from studylib.derive import derive
    _ev(course, "kc_created", {"kc_id": "k_hint", "name": "提示依赖测试"})
    _ev(course, "question_registered", {"question_id": "q_h", "kc_ids": ["k_hint"],
                                        "source_type": "homework", "transfer_level": "T0",
                                        "stem": "s", "answer": "a"})
    _ev(course, "hint_requested", {"question_id": "q_h", "level": 4})
    _ev(course, "question_attempted", {"question_id": "q_h", "correct": True, "hint_level": 4})
    state = derive(course)
    assert state["kc"]["k_hint"]["teaching_state"] == "practiced"
    assert state["state"]["next_best_step"]["action"] == "drill"
    _ev(course, "question_attempted", {"question_id": "q_h", "correct": True, "hint_level": 0})
    assert derive(course)["kc"]["k_hint"]["teaching_state"] == "checked"
