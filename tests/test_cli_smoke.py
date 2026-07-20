import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def run(args, cwd, env_home):
    import os
    env = dict(os.environ, STUDY_LOOP_HOME=str(env_home))
    return subprocess.run([sys.executable, *args], cwd=cwd, env=env,
                          capture_output=True, text=True)


def test_cli_full_smoke(tmp_path):
    home = tmp_path / "home"
    course_dir = tmp_path / "模电"

    r = run([SCRIPTS / "init_course.py", str(course_dir), "--course-id", "analog",
             "--name", "模拟电子技术", "--exam-date", "2026-07-25"], tmp_path, home)
    assert r.returncode == 0, r.stderr

    r = run([SCRIPTS / "event.py", "kc-add", "--kc-id", "feedback_topology",
             "--name", "反馈组态判断", "--exam-weight", "0.9"], course_dir, home)
    assert r.returncode == 0, r.stderr

    cand = course_dir / "q.json"
    cand.write_text(json.dumps({
        "question_id": "past_2023_q17", "kc_ids": ["feedback_topology"],
        "source_type": "past_exam", "transfer_level": "T0",
        "stem": "判断反馈组态", "answer": "A",
    }, ensure_ascii=False), encoding="utf-8")
    r = run([SCRIPTS / "validate_question.py", str(cand)], course_dir, home)
    assert r.returncode == 0, r.stderr

    r = run([SCRIPTS / "event.py", "attempt", "--question-id", "past_2023_q17",
             "--wrong", "--confidence", "0.9"], course_dir, home)
    assert r.returncode == 0, r.stderr
    assert "repair" in r.stdout or "下一步" in r.stdout

    r = run([SCRIPTS / "event.py", "misconception", "--error-id", "err_001",
             "--kc", "feedback_topology", "--question", "past_2023_q17",
             "--wrong-assumption", "有反馈连接即电压反馈",
             "--missing-premise", "必须检查取样方式",
             "--error-type", "concept_misconception"], course_dir, home)
    assert r.returncode == 0, r.stderr

    state = json.loads((course_dir / ".study" / "state.json").read_text(encoding="utf-8"))
    assert state["next_best_step"]["action"] == "repair"
    assert state["counts"]["weak"] == 1

    r = run([SCRIPTS / "fsrs.py", "create-card", "--card-type", "original_question",
             "--kc", "feedback_topology", "--question-id", "past_2023_q17"], course_dir, home)
    assert r.returncode == 0, r.stderr
    r = run([SCRIPTS / "fsrs.py", "due"], course_dir, home)
    assert r.returncode == 0 and "card_" in r.stdout

    r = run([SCRIPTS / "rebuild.py", "--dry-run"], course_dir, home)
    assert r.returncode == 0, r.stderr

    r = run([SCRIPTS / "next_step.py"], course_dir, home)
    assert r.returncode == 0 and "repair" in r.stdout


def test_cli_friendly_error_outside_course(tmp_path):
    r = run([SCRIPTS / "next_step.py"], tmp_path, tmp_path / "home")
    assert r.returncode == 1
    assert "course.yaml" in r.stderr + r.stdout


def test_evidence_and_misconception_show_labels(tmp_path):
    home = tmp_path / "home"
    course_dir = tmp_path / "模电"
    r = run([SCRIPTS / "init_course.py", str(course_dir), "--course-id", "analog",
             "--name", "模拟电子技术"], tmp_path, home)
    assert r.returncode == 0, r.stderr
    r = run([SCRIPTS / "event.py", "kc-add", "--kc-id", "feedback_topology",
             "--name", "反馈组态判断", "--exam-weight", "0.9"], course_dir, home)
    assert r.returncode == 0, r.stderr
    cand = course_dir / "q.json"
    cand.write_text(json.dumps({
        "question_id": "q1", "kc_ids": ["feedback_topology"], "source_type": "past_exam",
        "transfer_level": "T0", "stem": "判断反馈组态", "answer": "A",
    }, ensure_ascii=False), encoding="utf-8")
    assert run([SCRIPTS / "validate_question.py", str(cand)], course_dir, home).returncode == 0
    assert run([SCRIPTS / "event.py", "attempt", "--question-id", "q1",
                "--wrong", "--confidence", "0.9"], course_dir, home).returncode == 0
    assert run([SCRIPTS / "event.py", "misconception", "--error-id", "err_001",
                "--kc", "feedback_topology", "--question", "q1",
                "--wrong-assumption", "x", "--missing-premise", "y",
                "--error-type", "concept_misconception"], course_dir, home).returncode == 0

    r = run([SCRIPTS / "evidence.py", "--kc", "feedback_topology"], course_dir, home)
    assert r.returncode == 0, r.stderr
    assert "feedback_topology（反馈组态判断）" in r.stdout

    r = run([SCRIPTS / "misconception.py"], course_dir, home)
    assert r.returncode == 0, r.stderr
    assert "feedback_topology（反馈组态判断）" in r.stdout


def test_render_quiz_html_cli(tmp_path):
    home = tmp_path / "home"
    course_dir = tmp_path / "模电"
    assert run([SCRIPTS / "init_course.py", str(course_dir), "--course-id", "analog",
                "--name", "模拟电子技术"], tmp_path, home).returncode == 0
    manifest = course_dir / "m.json"
    manifest.write_text(json.dumps({
        "meta": {"course_id": "analog", "course_name": "模拟电子技术", "mode": "syllabus",
                 "count": 1, "generated_at": "2026-07-20T00:00:00+08:00"},
        "questions": [{"question_id": "q1", "kc_labels": ["k（名）"],
                       "stem": "Q\nA.x\nB.y", "answer": "A", "solution": "s"}],
    }, ensure_ascii=False), encoding="utf-8")
    out = course_dir / "quiz.html"
    r = run([SCRIPTS / "render_quiz_html.py", "--manifest", str(manifest),
             "--out", str(out), "--reveal-default", "on"], course_dir, home)
    assert r.returncode == 0, r.stderr
    text = out.read_text(encoding="utf-8")
    assert "id=\"revealToggle\"" in text and "模拟电子技术" in text


def test_drill_cli_produces_html(tmp_path):
    home = tmp_path / "home"
    course_dir = tmp_path / "模电"
    assert run([SCRIPTS / "init_course.py", str(course_dir), "--course-id", "analog",
                "--name", "模拟电子技术"], tmp_path, home).returncode == 0
    assert run([SCRIPTS / "event.py", "kc-add", "--kc-id", "feedback_topology",
                "--name", "反馈组态判断", "--exam-weight", "0.9"], course_dir, home).returncode == 0
    # register two MCQs
    for qid, ans in (("q1", "A"), ("q2", "B")):
        (course_dir / f"{qid}.json").write_text(json.dumps({
            "question_id": qid, "kc_ids": ["feedback_topology"], "source_type": "past_exam",
            "transfer_level": "T0", "stem": f"题 {qid}\nA.x\nB.y", "answer": ans,
        }, ensure_ascii=False), encoding="utf-8")
        assert run([SCRIPTS / "validate_question.py", str(course_dir / f"{qid}.json")],
                   course_dir, home).returncode == 0
    out_html = course_dir / "drill.html"
    r = run([SCRIPTS / "drill.py", "--mode", "syllabus", "--count", "2", "--format", "html",
             "--out", str(out_html), "--seed", "1"], course_dir, home)
    assert r.returncode == 0, r.stderr
    assert "feedback_topology（反馈组态判断）" in r.stdout  # summary uses labels
    assert out_html.exists() and "id=\"revealToggle\"" in out_html.read_text(encoding="utf-8")
