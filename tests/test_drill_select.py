import pytest


def _kc(state, weight=0.5):
    return {"kc_id": state, "name": state, "teaching_state": state, "exam_weight": weight,
            "prerequisites": [], "transfer": {}, "calibration": {}, "retention": {}}


def test_empty_and_zero_count():
    from studylib.drill import select_kcs
    assert select_kcs({}, "syllabus", 5) == []
    assert select_kcs({"a": _kc("unseen")}, "syllabus", 0) == []


def test_count_capped_to_available():
    from studylib.drill import select_kcs
    kcs = {"a": _kc("unseen"), "b": _kc("unseen")}
    assert set(select_kcs(kcs, "syllabus", 10, seed=1)) == {"a", "b"}


def test_deterministic_with_seed():
    from studylib.drill import select_kcs
    kcs = {f"k{i}": _kc("unseen", weight=(i + 1) / 5) for i in range(6)}
    r1 = select_kcs(kcs, "syllabus", 3, seed=42)
    r2 = select_kcs(kcs, "syllabus", 3, seed=42)
    assert r1 == r2 and len(r1) == 3


def test_unknown_mode_raises():
    from studylib.drill import select_kcs
    with pytest.raises(ValueError):
        select_kcs({"a": _kc("unseen")}, "bogus", 1)


def test_diagnostic_prefers_weak_in_distribution():
    # ES gives higher probability to higher weights, not certainty. Sample many
    # seeds and assert the frequency ordering the weights imply.
    from collections import Counter
    from studylib.drill import select_kcs
    kcs = {"weak": _kc("weak"), "conf": _kc("confirmed"), "unseen": _kc("unseen")}
    picks = Counter(select_kcs(kcs, "diagnostic", 1, seed=s)[0] for s in range(400))
    # weak (weight 1.0) selected most; unseen (0.4) next; confirmed (0.0) ~never
    assert picks["weak"] > picks["unseen"] > picks.get("confirmed", 0)
    # weak should win a clear majority (theoretical ~71%); >50% with large margin
    assert picks["weak"] > 200


def test_diagnostic_falls_back_when_all_unseen():
    from studylib.drill import select_kcs
    kcs = {"a": _kc("unseen", weight=0.9), "b": _kc("unseen", weight=0.1)}
    # all unseen -> behaves like syllabus; high-weight 'a' strongly preferred
    chosen = select_kcs(kcs, "diagnostic", 1, seed=0)
    assert chosen == ["a"]
