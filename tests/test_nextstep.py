COURSE = {"id": "c1", "name": "模电", "exam_date": None, "profile": {}}


def _kc_state(kc_id, state, *, weight=0.5, blind=0.0, t1=None, t2=None,
              retention=None, prereqs=()):
    return {
        "kc_id": kc_id, "name": kc_id, "chapter_id": None,
        "prerequisites": list(prereqs), "exam_weight": weight,
        "teaching_state": state,
        "retention": retention or {"fsrs_card_ids": [], "retrievability": None, "due_count": 0},
        "transfer": {"T0_original": None, "T1_near": t1, "T2_structural": t2,
                     "T3_discrimination": None, "T4_far": None},
        "calibration": {"self_estimate": None, "observed_performance": None,
                        "gap": None, "blind_spot": blind},
        "assistance": {"last_hint_level": 0, "independent_success_rate": None},
        "evidence_ids": [], "active_misconceptions": [],
    }


def _patch_name(kc_states, kc_id, name):
    kc_states[kc_id]["name"] = name


def test_repair_beats_confirmed():
    from studylib.nextstep import compute_next_best_step
    kc_states = {
        "good": _kc_state("good", "confirmed", weight=0.9),
        "bad": _kc_state("bad", "weak", weight=0.9, blind=0.3),
    }
    miscs = {"err_1": {"error_id": "err_1", "kc_ids": ["bad"], "repair_status": "active",
                       "error_type": "concept_misconception", "recurrence_count": 3,
                       "confidence_before": 0.9}}
    rec = compute_next_best_step(COURSE, kc_states, miscs, [])
    assert rec["action"] == "repair"
    assert rec["kc_id"] == "bad"
    assert rec["reasons"], "recommendation must be explainable"
    assert any("错因" in r or "高置信度" in r for r in rec["reasons"])


def test_review_when_only_due_cards():
    from studylib.nextstep import compute_next_best_step
    kc_states = {"good": _kc_state("good", "confirmed")}
    due = [{"card_id": "card_1", "kc_ids": ["good"], "due": "2026-01-01T00:00:00+00:00"}]
    rec = compute_next_best_step(COURSE, kc_states, {}, due)
    assert rec["action"] == "review"
    assert any("到期" in r for r in rec["reasons"])


def test_rest_when_nothing_to_do():
    from studylib.nextstep import compute_next_best_step
    rec = compute_next_best_step(COURSE, {"g": _kc_state("g", "confirmed")}, {}, [])
    assert rec["action"] == "rest"


def test_urgency_uses_exam_date():
    from studylib.nextstep import days_to_exam
    from datetime import date
    assert days_to_exam({"exam_date": "2026-07-25"}, today=date(2026, 7, 15)) == 10
    assert days_to_exam({"exam_date": None}) is None


def test_advance_for_unseen():
    from studylib.nextstep import compute_next_best_step
    rec = compute_next_best_step(COURSE, {"u": _kc_state("u", "unseen")}, {}, [])
    assert rec["action"] == "advance"
    assert rec["kc_id"] == "u"


def test_next_step_emits_kc_label():
    from studylib.nextstep import compute_next_best_step
    kc_states = {"u": _kc_state("u", "unseen")}
    _patch_name(kc_states, "u", "未知点")
    rec = compute_next_best_step(COURSE, kc_states, {}, [])
    assert rec["kc_label"] == "u（未知点）"
    assert rec["kc_name"] == "未知点"  # back-compat retained
