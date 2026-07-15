#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib.cli_common import guard, resolve_root
from studylib.ioutils import read_jsonl

app = typer.Typer(add_completion=False)


@app.command("list")
@guard
def list_cmd(
    kc: str = typer.Option(..., "--kc"),
    course: Path = typer.Option(None, "--course"),
):
    root = resolve_root(course)
    rows = [r for r in read_jsonl(root / ".study" / "evidence.jsonl") if kc in r["kc_ids"]]
    if not rows:
        typer.echo(f"KC {kc} 暂无证据")
        return
    for r in rows:
        mark = "✓" if r["result"]["correct"] else "✗"
        conf = r.get("confidence_before")
        typer.echo(f"{mark} {r['created_at']}  {r['question_id']}  {r['transfer_level']}  "
                   f"hint=L{r['hint_level']}  conf={conf if conf is not None else '-'}")


if __name__ == "__main__":
    app()
