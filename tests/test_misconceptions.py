def _ev(etype, payload):
    from studylib.events import new_event
    return new_event("c1", etype, payload)


MISC = {
    "kc_ids": ["k1"], "origin_question_id": "past_2023_q17",
    "wrong_assumption": "输出端存在反馈连接即可视为电压反馈",
    "missing_premise": "必须检查反馈网络对输出端的取样方式",
    "error_type": "concept_misconception",
    "trigger_conditions": ["复杂电路图"],
    "confidence_before": 0.9, "attribution_confidence": 0.82,
}

QS = {
    "past_2023_q17": {"question_id": "past_2023_q17", "kc_ids": ["k1"],
                      "source_type": "past_exam", "transfer_level": "T0"},
    "syn_t1": {"question_id": "syn_t1", "kc_ids": ["k1"],
               "source_type": "synthetic", "transfer_level": "T1"},
    "syn_t2": {"question_id": "syn_t2", "kc_ids": ["k1"],
               "source_type": "synthetic", "transfer_level": "T2"},
}


def test_new_misconception_defaults():
    from studylib.misconceptions import build_misconceptions
    ms = build_misconceptions([_ev("misconception_identified", MISC)], QS)
    (m,) = ms.values()
    assert m["repair_status"] == "active"
    assert m["recurrence_count"] == 1
    assert m["error_type"] == "concept_misconception"
    assert m["error_id"].startswith("err_")


def test_recurrence_merges_by_kc_and_type():
    from studylib.misconceptions import build_misconceptions
    again = dict(MISC, trigger_conditions=["多个输出节点"], origin_question_id="hw_q3")
    ms = build_misconceptions(
        [_ev("misconception_identified", MISC), _ev("misconception_identified", again)], QS)
    (m,) = ms.values()
    assert m["recurrence_count"] == 2
    assert set(m["trigger_conditions"]) == {"复杂电路图", "多个输出节点"}


def test_repair_and_dual_track_retest_resolves():
    from studylib.misconceptions import build_misconceptions
    e0 = _ev("misconception_identified", dict(MISC, error_id="err_001"))
    events = [
        e0,
        _ev("repair_started", {"error_id": "err_001", "repair_id": "repair_012"}),
        _ev("repair_completed", {"error_id": "err_001"}),
        _ev("question_attempted", {"question_id": "past_2023_q17", "correct": True,
                                   "retest_of_error_id": "err_001"}),
        _ev("transfer_test_attempted", {"question_id": "syn_t1", "correct": True,
                                        "retest_of_error_id": "err_001"}),
    ]
    ms = build_misconceptions(events, QS)
    m = ms["err_001"]
    assert m["repair_status"] == "resolved"
    assert m["repair_history"] == ["repair_012"]


def test_failed_transfer_retest_reactivates():
    from studylib.misconceptions import build_misconceptions
    events = [
        _ev("misconception_identified", dict(MISC, error_id="err_001")),
        _ev("repair_completed", {"error_id": "err_001"}),
        _ev("transfer_test_attempted", {"question_id": "syn_t2", "correct": False,
                                        "retest_of_error_id": "err_001"}),
    ]
    m = build_misconceptions(events, QS)["err_001"]
    assert m["repair_status"] == "active"
    assert m["transfer_failures"] == ["syn_t2"]


def test_active_high_confidence_helper():
    from studylib.misconceptions import active_high_confidence, build_misconceptions
    ms = build_misconceptions([_ev("misconception_identified", dict(MISC, error_id="err_001"))], QS)
    assert active_high_confidence(ms, "k1") is True
    assert active_high_confidence(ms, "k2") is False
