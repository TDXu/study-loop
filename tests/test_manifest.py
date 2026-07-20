from studylib.manifest import build_manifest


def test_manifest_shape_and_meta():
    course = {"id": "mao-zhongte", "name": "毛中特"}
    qs = [{"question_id": "q1", "kc_ids": ["mao_living_soul"], "stem": "s", "answer": "A",
           "solution": "sol", "difficulty": 0.4, "transfer_level": "T0",
           "validation": {"generator": {}}}]
    m = build_manifest(course, "diagnostic", 5, qs,
                       kcs={"mao_living_soul": {"name": "毛泽东思想活的灵魂"}})
    assert m["meta"] == {k: m["meta"][k] for k in
                         ("course_id", "course_name", "mode", "count", "generated_at")}
    assert m["meta"]["course_name"] == "毛中特" and m["meta"]["count"] == 5
    assert len(m["questions"]) == 1
    q = m["questions"][0]
    assert q["question_id"] == "q1"
    assert q["kc_labels"] == ["mao_living_soul（毛泽东思想活的灵魂）"]
    assert "validation" not in q  # rendering does not need it
    assert q["answer"] == "A" and q["solution"] == "sol"


def test_manifest_no_kcs_falls_back_to_ids():
    m = build_manifest({"id": "c", "name": "C"}, "syllabus", 3,
                       [{"question_id": "q", "kc_ids": ["k"], "stem": "", "answer": "B"}])
    assert m["questions"][0]["kc_labels"] == ["k"]
