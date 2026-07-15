#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib import derive as derive_mod
from studylib.cli_common import guard, resolve_root
from studylib.ioutils import course_lock

app = typer.Typer(add_completion=False)


@app.command()
@guard
def main(course: Path = typer.Option(None, "--course")):
    root = resolve_root(course)
    with course_lock(root):
        derive_mod.derive(root)
    typer.echo((root / ".study" / "dashboard.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    app()
