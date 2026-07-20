#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib.cli_common import guard
from studylib.ioutils import read_json
from studylib.render_paper import manifest_to_markdown, markdown_to_pdf

app = typer.Typer(add_completion=False)


@app.command()
@guard
def main(
    manifest: Path = typer.Option(..., "--manifest"),
    variant: str = typer.Option("both", "--variant"),
    out_dir: Path = typer.Option(None, "--out-dir"),
    fonts_dir: Path = typer.Option(None, "--fonts-dir"),
):
    if variant not in ("questions", "answers", "both"):
        typer.echo("错误：--variant 必须是 questions/answers/both", err=True)
        raise typer.Exit(code=1)
    m = read_json(manifest)
    if not m:
        typer.echo(f"错误：manifest 不存在或为空：{manifest}", err=True)
        raise typer.Exit(code=1)
    out_dir = out_dir or manifest.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    base = m["meta"].get("course_name", "quiz")
    variants = ["questions", "answers"] if variant == "both" else [variant]
    for v in variants:
        md = manifest_to_markdown(m, v)
        tag = "题目" if v == "questions" else "答案解析"
        pdf = out_dir / f"{base}-{tag}.pdf"
        markdown_to_pdf(md, pdf, fonts_dir=fonts_dir)
        typer.echo(f"已生成：{pdf}")


if __name__ == "__main__":
    app()
