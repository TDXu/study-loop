#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib.cli_common import guard
from studylib.ioutils import atomic_write_text, read_json
from studylib.render_html import render_quiz_html

app = typer.Typer(add_completion=False)


@app.command()
@guard
def main(
    manifest: Path = typer.Option(..., "--manifest"),
    out: Path = typer.Option(None, "--out"),
    reveal_default: str = typer.Option("on", "--reveal-default"),
):
    m = read_json(manifest)
    if not m:
        typer.echo(f"错误：manifest 不存在或为空：{manifest}", err=True)
        raise typer.Exit(code=1)
    html = render_quiz_html(m, reveal_default == "on")
    out = out or manifest.with_suffix(".html")
    atomic_write_text(out, html)
    typer.echo(f"已生成交互测验页：{out}")


if __name__ == "__main__":
    app()
