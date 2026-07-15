#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib import derive as derive_mod
from studylib.cli_common import guard
from studylib.course import init_course
from studylib.ioutils import course_lock

app = typer.Typer(add_completion=False)


@app.command()
@guard
def main(
    path: Path = typer.Argument(..., help="课程工作区目录"),
    course_id: str = typer.Option(..., "--course-id"),
    name: str = typer.Option(..., "--name"),
    exam_date: str = typer.Option(None, "--exam-date", help="YYYY-MM-DD"),
):
    root = init_course(path, course_id, name, exam_date)
    with course_lock(root):
        derive_mod.derive(root)
    typer.echo(f"课程工作区已创建：{root}")


if __name__ == "__main__":
    app()
