#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib.cli_common import guard, resolve_root
from studylib.derive import rebuild as rebuild_fn
from studylib.ioutils import course_lock

app = typer.Typer(add_completion=False)


@app.command()
@guard
def main(
    course: Path = typer.Option(None, "--course"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    root = resolve_root(course)
    with course_lock(root):
        summary = rebuild_fn(root, dry_run=dry_run)
    typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
