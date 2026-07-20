from studylib.render_html import parse_options, render_quiz_html


def test_parse_options_half_and_full_width():
    body, opts = parse_options("毛泽东思想活的灵魂是（  ）\nA.实事求是\nB.群众路线\nC.独立自主\nD.统一战线")
    assert body == "毛泽东思想活的灵魂是（  ）"
    assert opts == [("A", "实事求是"), ("B", "群众路线"), ("C", "独立自主"), ("D", "统一战线")]


def test_parse_options_full_width_dot():
    _, opts = parse_options("Q\nＡ．甲\nＢ．乙")
    assert opts == [("A", "甲"), ("B", "乙")]


def test_parse_options_none():
    body, opts = parse_options("简答题：论述…")
    assert body == "简答题：论述…" and opts == []


def test_parse_option_continuation_line():
    _, opts = parse_options("Q\nA.第一行\n续行\nB.第二项")
    assert opts == [("A", "第一行 续行"), ("B", "第二项")]


def _manifest(multi=False):
    return {
        "meta": {"course_name": "毛中特", "mode": "diagnostic", "count": 1,
                 "generated_at": "2026-07-20T00:00:00+08:00"},
        "questions": [{
            "kc_labels": ["mao_living_soul（毛泽东思想活的灵魂）"],
            "stem": "活的灵魂三个方面是（  ）\nA.实事求是\nB.群众路线\nC.独立自主",
            "answer": "ABC" if multi else "A",
            "solution": "实事求是/群众路线/独立自主。",
        }],
    }


def test_render_html_embeds_toggle_options_answers():
    html = render_quiz_html(_manifest(multi=True), reveal_default=True)
    assert 'id="revealToggle"' in html
    # toggle ON -> the toggle input carries 'checked'
    assert 'revealToggle" checked' in html
    assert "mao_living_soul（毛泽东思想活的灵魂）" in html
    # multi -> checkbox; single would be radio
    assert 'type="checkbox"' in html
    # answer + solution embedded (hidden by CSS until reveal)
    assert "ABC" in html and "实事求是/群众路线/独立自主" in html


def test_render_html_reveal_default_off_not_checked():
    html = render_quiz_html(_manifest(multi=False), reveal_default=False)
    assert 'type="radio"' in html
    # toggle OFF -> the toggle input must NOT carry 'checked'
    toggle_line = html.split('id="revealToggle"', 1)[1].split(">", 1)[0]
    assert "checked" not in toggle_line


def test_lowercase_answer_normalized_for_grading():
    # options normalized to uppercase; answer must match that normalization
    m = {
        "meta": {"course_name": "C", "mode": "syllabus", "count": 1,
                 "generated_at": "2026-07-20T00:00:00+08:00"},
        "questions": [{"kc_labels": ["k（名）"], "stem": "Q\nA.x\nB.y\nC.z",
                       "answer": "abc", "solution": "s"}],
    }
    html = render_quiz_html(m, reveal_default=True)
    # grading attribute uses uppercase; displayed answer is uppercase too
    assert 'data-answer="A,B,C"' in html
    assert "答案：<b>ABC</b>" in html


def test_user_text_is_html_escaped():
    m = {
        "meta": {"course_name": "C", "mode": "syllabus", "count": 1,
                 "generated_at": "2026-07-20T00:00:00+08:00"},
        "questions": [{"kc_labels": ["k（名）"], "stem": "若 a < b 且 b > c\nA.x\nB.y",
                       "answer": "A", "solution": "解析：a & b 的关系"}],
    }
    html = render_quiz_html(m, reveal_default=True)
    assert "&lt;" in html and "&gt;" in html and "&amp;" in html
    # literal user substring must NOT appear unescaped anywhere in the output
    assert "a < b" not in html
    assert "a &lt; b" in html


def test_two_questions_have_distinct_radio_groups():
    m = {
        "meta": {"course_name": "C", "mode": "syllabus", "count": 2,
                 "generated_at": "2026-07-20T00:00:00+08:00"},
        "questions": [
            {"kc_labels": [], "stem": "Q1\nA.x\nB.y", "answer": "A", "solution": ""},
            {"kc_labels": [], "stem": "Q2\nA.x\nB.y", "answer": "B", "solution": ""},
        ],
    }
    html = render_quiz_html(m, reveal_default=False)
    assert 'name="q1"' in html and 'name="q2"' in html
