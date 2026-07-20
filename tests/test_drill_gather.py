def _q(qid, kcs):
    return {"question_id": qid, "kc_ids": kcs, "stem": "", "answer": "A"}


def test_enough_questions_no_shortfall():
    from studylib.drill import gather_questions
    questions = {
        "a1": _q("a1", ["k1"]), "a2": _q("a2", ["k1"]), "a3": _q("a3", ["k1"]),
        "b1": _q("b1", ["k2"]), "b2": _q("b2", ["k2"]),
    }
    picked, short = gather_questions(questions, ["k1", "k2"], per_kc=2, total=4)
    assert len(picked) == 4
    assert short == {}


def test_shortfall_when_kc_has_no_questions():
    from studylib.drill import gather_questions
    questions = {"a1": _q("a1", ["k1"]), "a2": _q("a2", ["k1"])}
    picked, short = gather_questions(questions, ["k1", "k2"], per_kc=2, total=4)
    assert short == {"k2": 2}
    assert all(q["kc_ids"] == ["k1"] for q in picked)


def test_total_cap_respected():
    from studylib.drill import gather_questions
    questions = {f"a{i}": _q(f"a{i}", ["k1"]) for i in range(5)}
    questions.update({f"b{i}": _q(f"b{i}", ["k2"]) for i in range(5)})
    picked, short = gather_questions(questions, ["k1", "k2"], per_kc=2, total=2)
    assert len(picked) == 2
    assert short == {}


def test_multi_kc_question_not_duplicated():
    from studylib.drill import gather_questions
    questions = {
        "q1": _q("q1", ["k1", "k2"]),
        "q2": _q("q2", ["k1"]),
        "q3": _q("q3", ["k2"]),
    }
    picked, short = gather_questions(questions, ["k1", "k2"], per_kc=2, total=4)
    ids = [q["question_id"] for q in picked]
    assert len(ids) == len(set(ids)), f"duplicate questions: {ids}"
    assert set(ids) == {"q1", "q2", "q3"}
