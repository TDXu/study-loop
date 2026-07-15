from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=8))
T0 = datetime(2026, 7, 10, 10, 0, 0, tzinfo=TZ)


def _row(kc, correct, *, hint=0, level="T0", conf=None, at_hours=0):
    return {
        "kc_ids": [kc], "result": {"correct": correct, "score": 1.0 if correct else 0.0},
        "hint_level": hint, "transfer_level": level, "confidence_before": conf,
        "created_at": (T0 + timedelta(hours=at_hours)).isoformat(),
        "evidence_id": f"evd_{kc}_{at_hours}", "question_id": f"q_{at_hours}",
    }


def _kc(kc_id, prereqs=(), explained=False, weight=0.5):
    return {"kc_id": kc_id, "name": kc_id, "chapter_id": None,
            "prerequisites": list(prereqs), "exam_weight": weight,
            "source_ids": [], "explained": explained}


def _states(kcs, evidence, miscs=None):
    from studylib.state_rules import compute_kc_states
    return compute_kc_states(kcs, evidence, miscs or {})


def test_unseen_and_explained():
    kcs = {"a": _kc("a"), "b": _kc("b", explained=True)}
    out = _states(kcs, [])
    assert out["a"]["teaching_state"] == "unseen"
    assert out["b"]["teaching_state"] == "explained"


def test_practiced_when_only_assisted_success():
    # L4 提示下答对 → 不允许 checked（spec §14.1 / 场景 C）
    out = _states({"a": _kc("a")}, [_row("a", True, hint=4)])
    assert out["a"]["teaching_state"] == "practiced"


def test_checked_on_independent_correct():
    out = _states({"a": _kc("a")}, [_row("a", True, hint=1)])
    assert out["a"]["teaching_state"] == "checked"


def test_weak_on_last_wrong_and_high_conf_misconception():
    out = _states({"a": _kc("a")}, [_row("a", True), _row("a", False, conf=0.9, at_hours=1)])
    assert out["a"]["teaching_state"] == "weak"
    miscs = {"err_1": {"error_id": "err_1", "kc_ids": ["a"], "repair_status": "active",
                       "confidence_before": 0.9}}
    out2 = _states({"a": _kc("a")}, [_row("a", True)], miscs)
    assert out2["a"]["teaching_state"] == "weak"
    assert out2["a"]["active_misconceptions"] == ["err_1"]


def test_confirmed_needs_retention_and_transfer():
    rows = [
        _row("a", True, at_hours=0),
        _row("a", True, level="T1", at_hours=30),  # 隔 >1 天 + T1 通过
    ]
    out = _states({"a": _kc("a")}, rows)
    assert out["a"]["teaching_state"] == "confirmed"
    # 无迁移证据 → 只能 checked
    rows_no_transfer = [_row("a", True, at_hours=0), _row("a", True, at_hours=30)]
    out2 = _states({"a": _kc("a")}, rows_no_transfer)
    assert out2["a"]["teaching_state"] == "checked"


def test_blocked_by_weak_prerequisite():
    kcs = {"pre": _kc("pre"), "post": _kc("post", prereqs=["pre"])}
    rows = [_row("pre", False), _row("post", True, hint=4, at_hours=1)]
    out = _states(kcs, rows)
    assert out["pre"]["teaching_state"] == "weak"
    assert out["post"]["teaching_state"] == "blocked"


def test_transfer_vector_and_calibration_shape():
    rows = [_row("a", False, conf=0.9), _row("a", True, level="T1", conf=0.8, at_hours=1)]
    out = _states({"a": _kc("a")}, rows)
    kc = out["a"]
    assert kc["transfer"]["T0_original"] == 0.0
    assert kc["transfer"]["T1_near"] == 1.0
    assert kc["transfer"]["T3_discrimination"] is None
    assert abs(kc["calibration"]["self_estimate"] - 0.85) < 1e-9
    assert kc["calibration"]["observed_performance"] == 0.5
    assert abs(kc["calibration"]["gap"] - 0.35) < 1e-9
    assert kc["retention"] == {"fsrs_card_ids": [], "retrievability": None, "due_count": 0}
