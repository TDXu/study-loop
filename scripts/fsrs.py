#!/usr/bin/env python3
"""FSRS card management CLI.

NOTE: This file is named 'fsrs.py' which shadows the 'fsrs' pip package
when scripts/ is on sys.path. The bootstrap below moves scripts/ to the
END of sys.path so the real package is found first.
"""
import sys
from pathlib import Path

_scripts_dir = str(Path(__file__).resolve().parent)

# Ensure the 'fsrs' pip package is found before this file when studylib
# sub-modules do 'from fsrs import Card, Rating, Scheduler'.
# Remove scripts/ from sys.path, let site-packages resolve first, then
# re-append scripts/ so 'studylib' is still importable.
sys.path = [p for p in sys.path if p != _scripts_dir]
sys.path.append(_scripts_dir)

import typer  # noqa: E402

from studylib.cli_common import commit_events, echo_next, guard, resolve_root  # noqa: E402
from studylib.course import load_course  # noqa: E402
from studylib.events import new_event, read_events  # noqa: E402
from studylib.fsrs_store import due_cards, new_card_payload, replay_cards  # noqa: E402
from studylib.ioutils import now_iso  # noqa: E402

app = typer.Typer(add_completion=False)


@app.command("create-card")
@guard
def create_card(
    card_type: str = typer.Option(..., "--card-type"),
    kc: list[str] = typer.Option(..., "--kc"),
    question_id: str = typer.Option(None, "--question-id"),
    course: Path = typer.Option(None, "--course"),
):
    root = resolve_root(course)
    cid = load_course(root)["id"]
    payload = new_card_payload(card_type, list(kc), question_id)
    commit_events(root, [new_event(cid, "fsrs_card_created", payload)])
    typer.echo(f"卡片已创建：{payload['card_id']}")


@app.command()
@guard
def review(
    card_id: str = typer.Option(..., "--card-id"),
    rating: int = typer.Option(..., "--rating", min=1, max=4),
    course: Path = typer.Option(None, "--course"),
):
    root = resolve_root(course)
    cid = load_course(root)["id"]
    state = commit_events(root, [new_event(cid, "fsrs_reviewed", {
        "card_id": card_id, "rating": rating, "review_time": now_iso()})])
    typer.echo("复习已记录")
    echo_next(state)


@app.command()
@guard
def due(course: Path = typer.Option(None, "--course")):
    root = resolve_root(course)
    cards = replay_cards(read_events(root))
    rows = due_cards(cards)
    if not rows:
        typer.echo("没有到期卡片")
        return
    for c in rows:
        typer.echo(f"{c['card_id']}  {c['card_type']}  kc={','.join(c['kc_ids'])}  due={c['due']}")


if __name__ == "__main__":
    app()
