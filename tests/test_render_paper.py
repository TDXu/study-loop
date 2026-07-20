from studylib.render_paper import manifest_to_markdown

M = {
    "meta": {"course_name": "毛中特", "mode": "syllabus", "count": 1,
             "generated_at": "2026-07-20T00:00:00+08:00"},
    "questions": [{"question_id": "q1", "kc_labels": ["k（名）"],
                   "stem": "活的灵魂三方面是（  ）\nA.实事求是\nB.群众路线",
                   "answer": "A", "solution": "实事求是是根本观点。"}],
}


def test_questions_variant_has_no_answer():
    md = manifest_to_markdown(M, "questions")
    assert "活的灵魂三方面是" in md and "A.实事求是" in md
    assert "答案" not in md and "实事求是是根本观点" not in md


def test_answers_variant_has_answer_and_solution():
    md = manifest_to_markdown(M, "answers")
    assert "答案：A" in md and "实事求是是根本观点" in md


def test_markdown_to_pdf_produces_file(tmp_path):
    from studylib.render_paper import manifest_to_markdown, markdown_to_pdf
    md = manifest_to_markdown(M, "answers")
    pdf = tmp_path / "out.pdf"
    markdown_to_pdf(md, pdf, fonts_dir=None)  # CID fallback, no font files needed
    assert pdf.exists() and pdf.stat().st_size > 0
    assert pdf.read_bytes()[:5] == b"%PDF-"
