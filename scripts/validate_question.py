#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib import derive as derive_mod
from studylib.cli_common import guard, resolve_root
from studylib.ioutils import course_lock
from studylib.validation import register_question

app = typer.Typer(add_completion=False)


@app.command()
@guard
def main(
    candidate: Path = typer.Argument(..., help="候选题 JSON 文件"),
    as_transfer_test: bool = typer.Option(False, "--as-transfer-test"),
    course: Path = typer.Option(None, "--course"),
):
    root = resolve_root(course)
    cand = json.loads(candidate.read_text(encoding="utf-8"))
    with course_lock(root):
        ev = register_question(root, cand, as_transfer_test=as_transfer_test)
        derive_mod.derive(root)
    typer.echo(f"题目已通过闸门并注册：{ev['payload']['question_id']}（{ev['event_type']}）")


if __name__ == "__main__":
    app()
