from studylib.display import kc_label


def test_label_with_chinese_name():
    kcs = {"mao_living_soul": {"name": "毛泽东思想活的灵魂"}}
    assert kc_label("mao_living_soul", kcs) == "mao_living_soul（毛泽东思想活的灵魂）"


def test_label_missing_kc_falls_back_to_id():
    assert kc_label("orphan", {"x": {"name": "X"}}) == "orphan"


def test_label_no_kcs_arg():
    assert kc_label("orphan") == "orphan"


def test_label_name_equals_id():
    assert kc_label("x", {"x": {"name": "x"}}) == "x"


def test_label_empty_name_falls_back():
    assert kc_label("x", {"x": {"name": ""}}) == "x"
