#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib.cli_common import commit_events, echo_next, guard, resolve_root
from studylib.course import load_course
from studylib.events import new_event
from studylib.schemas import ERROR_TYPES

app = typer.Typer(add_completion=False)


def _ctx(course: Path | None):
    root = resolve_root(course)
    return root, load_course(root)["id"]


@app.command("kc-add")
@guard
def kc_add(
    kc_id: str = typer.Option(..., "--kc-id"),
    name: str = typer.Option(..., "--name"),
    chapter: str = typer.Option(None, "--chapter"),
    prereq: list[str] = typer.Option([], "--prereq"),
    exam_weight: float = typer.Option(0.5, "--exam-weight"),
    source_id: list[str] = typer.Option([], "--source-id"),
    course: Path = typer.Option(None, "--course"),
):
    root, cid = _ctx(course)
    state = commit_events(root, [new_event(cid, "kc_created", {
        "kc_id": kc_id, "name": name, "chapter_id": chapter,
        "prerequisites": list(prereq), "exam_weight": exam_weight,
        "source_ids": list(source_id)})])
    typer.echo(f"KC 已注册：{kc_id}")
    echo_next(state)


@app.command("kc-explained")
@guard
def kc_explained(
    kc_id: str = typer.Option(..., "--kc-id"),
    course: Path = typer.Option(None, "--course"),
):
    root, cid = _ctx(course)
    state = commit_events(root, [new_event(cid, "kc_updated", {"kc_id": kc_id, "update": "explained"})])
    echo_next(state)


@app.command("source-add")
@guard
def source_add(
    source_id: str = typer.Option(..., "--source-id"),
    source_type: str = typer.Option(..., "--source-type"),
    file: str = typer.Option(..., "--file"),
    section: str = typer.Option(None, "--section"),
    course: Path = typer.Option(None, "--course"),
):
    root, cid = _ctx(course)
    commit_events(root, [new_event(cid, "source_registered", {
        "source_id": source_id, "source_type": source_type, "file": file, "section": section})])
    typer.echo(f"来源已登记：{source_id}")


@app.command()
@guard
def attempt(
    question_id: str = typer.Option(..., "--question-id"),
    correct: bool = typer.Option(..., "--correct/--wrong"),
    confidence: float = typer.Option(None, "--confidence", min=0.0, max=1.0),
    hint_level: int = typer.Option(0, "--hint-level", min=0, max=5),
    time_sec: int = typer.Option(None, "--time-sec"),
    retest_of: str = typer.Option(None, "--retest-of"),
    transfer: bool = typer.Option(False, "--transfer", help="记为 transfer_test_attempted"),
    session: str = typer.Option("session_adhoc", "--session"),
    course: Path = typer.Option(None, "--course"),
):
    root, cid = _ctx(course)
    events = []
    if confidence is not None:
        events.append(new_event(cid, "confidence_recorded",
                                {"question_id": question_id, "confidence_before": confidence},
                                session_id=session))
    payload = {"question_id": question_id, "correct": correct, "hint_level": hint_level}
    if confidence is not None:
        payload["confidence_before"] = confidence
    if time_sec is not None:
        payload["response_time_sec"] = time_sec
    if retest_of:
        payload["retest_of_error_id"] = retest_of
    etype = "transfer_test_attempted" if transfer else "question_attempted"
    events.append(new_event(cid, etype, payload, session_id=session))
    state = commit_events(root, events)
    typer.echo("已记录：" + ("答对" if correct else "答错"))
    echo_next(state)


@app.command()
@guard
def hint(
    question_id: str = typer.Option(..., "--question-id"),
    level: int = typer.Option(..., "--level", min=1, max=5),
    course: Path = typer.Option(None, "--course"),
):
    root, cid = _ctx(course)
    commit_events(root, [new_event(cid, "hint_requested", {"question_id": question_id, "level": level})])
    typer.echo(f"已记录 L{level} 提示")


@app.command()
@guard
def misconception(
    error_id: str = typer.Option(None, "--error-id"),
    kc: list[str] = typer.Option(..., "--kc"),
    question: str = typer.Option(None, "--question"),
    wrong_assumption: str = typer.Option(..., "--wrong-assumption"),
    missing_premise: str = typer.Option(..., "--missing-premise"),
    error_type: str = typer.Option(..., "--error-type"),
    trigger: list[str] = typer.Option([], "--trigger"),
    confidence_before: float = typer.Option(None, "--confidence-before"),
    attribution_confidence: float = typer.Option(None, "--attribution-confidence"),
    course: Path = typer.Option(None, "--course"),
):
    if error_type not in ERROR_TYPES:
        typer.echo(f"错误：未知错因类型 {error_type}（可选：{sorted(ERROR_TYPES)}）", err=True)
        raise typer.Exit(code=1)
    root, cid = _ctx(course)
    payload = {"kc_ids": list(kc), "origin_question_id": question,
               "wrong_assumption": wrong_assumption, "missing_premise": missing_premise,
               "error_type": error_type, "trigger_conditions": list(trigger),
               "confidence_before": confidence_before,
               "attribution_confidence": attribution_confidence}
    if error_id:
        payload["error_id"] = error_id
    state = commit_events(root, [new_event(cid, "misconception_identified", payload)])
    typer.echo("错因已入库（Misconception Memory）")
    echo_next(state)


@app.command("repair-start")
@guard
def repair_start(
    error_id: str = typer.Option(..., "--error-id"),
    repair_id: str = typer.Option(..., "--repair-id"),
    course: Path = typer.Option(None, "--course"),
):
    root, cid = _ctx(course)
    commit_events(root, [new_event(cid, "repair_started", {"error_id": error_id, "repair_id": repair_id})])
    typer.echo(f"修复开始：{repair_id}")


@app.command("repair-step")
@guard
def repair_step(
    error_id: str = typer.Option(..., "--error-id"),
    note: str = typer.Option(None, "--note"),
    course: Path = typer.Option(None, "--course"),
):
    root, cid = _ctx(course)
    commit_events(root, [new_event(cid, "repair_step_completed", {"error_id": error_id, "note": note})])


@app.command("repair-done")
@guard
def repair_done(
    error_id: str = typer.Option(..., "--error-id"),
    course: Path = typer.Option(None, "--course"),
):
    root, cid = _ctx(course)
    state = commit_events(root, [new_event(cid, "repair_completed", {"error_id": error_id})])
    typer.echo("修复完成，进入重测（原题二刷 + 迁移验证）")
    echo_next(state)


if __name__ == "__main__":
    app()
