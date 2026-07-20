#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib.cli_common import guard, resolve_root
from studylib.display import kc_label
from studylib.ioutils import read_json, read_jsonl

app = typer.Typer(add_completion=False)


@app.command("list")
@guard
def list_cmd(course: Path = typer.Option(None, "--course")):
    root = resolve_root(course)
    rows = read_jsonl(root / ".study" / "errors.jsonl")
    active = [m for m in rows if m.get("repair_status") != "resolved"]
    if not active:
        typer.echo("没有活跃错因")
        return
    kcs = read_json(root / ".study" / "kc.json")
    for m in active:
        kc_disp = " / ".join(kc_label(k, kcs) for k in m["kc_ids"])
        typer.echo(f"{m['error_id']}  [{m['repair_status']}]  {m['error_type']}  "
                   f"kc={kc_disp}  ×{m.get('recurrence_count', 1)}")
        typer.echo(f"    错误假设：{m.get('wrong_assumption', '')}")


if __name__ == "__main__":
    app()
