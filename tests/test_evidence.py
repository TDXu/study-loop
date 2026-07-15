def _attempt(qid, correct, *, conf=None, hint=0, kc_ids=None, retest=None, etype="question_attempted"):
    from studylib.events import new_event
    p = {"question_id": qid, "correct": correct, "hint_level": hint}
    if conf is not None:
        p["confidence_before"] = conf
    if kc_ids:
        p["kc_ids"] = kc_ids
    if retest:
        p["retest_of_error_id"] = retest
    return new_event("c1", etype, p)


QS = {
    "past_2023_q17": {"question_id": "past_2023_q17", "kc_ids": ["k1"],
                      "source_type": "past_exam", "transfer_level": "T0"},
    "syn_q_018": {"question_id": "syn_q_018", "kc_ids": ["k1"],
                  "source_type": "synthetic", "transfer_level": "T2"},
}


def test_evidence_from_attempt():
    from studylib.evidence import build_evidence
    ev = _attempt("past_2023_q17", False, conf=0.9)
    rows = build_evidence([ev], QS)
    assert len(rows) == 1
    r = rows[0]
    assert r["evidence_id"] == "evd_" + ev["event_id"][4:]
    assert r["kc_ids"] == ["k1"]
    assert r["result"] == {"correct": False, "score": 0.0}
    assert r["confidence_before"] == 0.9
    assert r["transfer_level"] == "T0"
    assert r["source_event_id"] == ev["event_id"]


def test_evidence_transfer_level_from_registry():
    from studylib.evidence import build_evidence
    rows = build_evidence([_attempt("syn_q_018", True, etype="transfer_test_attempted")], QS)
    assert rows[0]["transfer_level"] == "T2"
    assert rows[0]["result"]["score"] == 1.0


def test_evidence_unregistered_question_defaults_t0():
    from studylib.evidence import build_evidence
    rows = build_evidence([_attempt("mystery_q", True, kc_ids=["k9"])], {})
    assert rows[0]["transfer_level"] == "T0"
    assert rows[0]["kc_ids"] == ["k9"]
