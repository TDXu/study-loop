#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import typer

from studylib import derive as derive_mod
from studylib.cli_common import guard, resolve_root
from studylib.course import load_course
from studylib.display import kc_label
from studylib.drill import gather_questions, select_kcs
from studylib.ioutils import atomic_write_json, atomic_write_text, course_lock
from studylib.manifest import build_manifest
from studylib.render_html import render_quiz_html
from studylib.render_paper import manifest_to_markdown, markdown_to_pdf

app = typer.Typer(add_completion=False)

NEXT_STEP_HINT = {
    "syllabus": "做完后对命中的同知识点做复盘重测（迁移题），验证不是背题。",
    "diagnostic": "据作答结果，对命中的弱知识点针对性出题 / 修复错因。",
}


@app.command()
@guard
def main(
    mode: str = typer.Option(..., "--mode"),
    count: int = typer.Option(10, "--count"),
    per_kc: int = typer.Option(2, "--per-kc"),
    fmt: str = typer.Option("html", "--format"),
    out: Path = typer.Option(None, "--out"),
    reveal_default: str = typer.Option("on", "--reveal-default"),
    seed: int = typer.Option(0, "--seed"),
    fonts_dir: Path = typer.Option(None, "--fonts-dir"),
    course: Path = typer.Option(None, "--course"),
):
    if mode not in ("syllabus", "diagnostic"):
        typer.echo("错误：--mode 必须是 syllabus 或 diagnostic", err=True)
        raise typer.Exit(code=1)
    if fmt not in ("html", "paper", "md"):
        typer.echo("错误：--format 必须是 html / paper / md", err=True)
        raise typer.Exit(code=1)

    root = resolve_root(course)
    with course_lock(root):
        result = derive_mod.derive(root)
    kc_states = result["kc"]
    questions = result["questions"]
    course_doc = load_course(root)

    selected = select_kcs(kc_states, mode, count, seed)
    picked, shortfall = gather_questions(questions, selected, per_kc=per_kc, total=count)
    manifest = build_manifest(course_doc, mode, count, picked, kcs=kc_states)

    out = out or (root / "output" / f"drill-{mode}-{count}")
    out.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "html":
        html_path = out.with_suffix(".html")
        atomic_write_text(html_path, render_quiz_html(manifest, reveal_default == "on"))
        typer.echo(f"已生成交互测验页：{html_path}")
    elif fmt == "paper":
        for v, tag in (("questions", "题目"), ("answers", "答案解析")):
            pdf = out.parent / f"{out.name}-{tag}.pdf"
            markdown_to_pdf(manifest_to_markdown(manifest, v), pdf, fonts_dir=fonts_dir)
            typer.echo(f"已生成 PDF：{pdf}")
    else:  # md
        md_path = out.with_suffix(".md")
        atomic_write_text(md_path, manifest_to_markdown(manifest, "answers"))
        typer.echo(f"已生成 Markdown：{md_path}")
    atomic_write_json(out.with_suffix(".manifest.json"), manifest)

    typer.echo("\n选题（按权重）：")
    for kc_id in selected:
        typer.echo(f"  - {kc_label(kc_id, kc_states)}")
    typer.echo(f"实际凑题：{len(picked)} 题（目标 {count}）。")
    if shortfall:
        typer.echo("⚠️ 题量不足（注册表缺题，未自动走 AI 出题闸门）：")
        for k, miss in shortfall.items():
            typer.echo(f"  - {kc_label(k, kc_states)}：缺 {miss} 题")
    typer.echo(f"\n下一步建议：{NEXT_STEP_HINT[mode]}")


if __name__ == "__main__":
    app()
