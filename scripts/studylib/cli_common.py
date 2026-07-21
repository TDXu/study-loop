from __future__ import annotations

import functools
from pathlib import Path

import typer

from . import derive as derive_mod
from .errors import StudyLoopError
from .events import append_event
from .ioutils import course_lock
from .paths import find_course_root


def resolve_root(path: Path | None) -> Path:
    return find_course_root(path)


def commit_events(root: Path, events: list[dict]) -> dict:
    with course_lock(root):
        for ev in events:
            append_event(root, ev)
        result = derive_mod.derive(root)
    return result["state"]


def echo_next(state: dict) -> None:
    nbs = state["next_best_step"]
    if nbs["action"] == "rest":
        typer.echo(f"下一步建议：rest —— {nbs['reasons'][0]}")
        return
    target = nbs.get("kc_label") or nbs.get("kc_name") or "到期复习"
    typer.echo(f"下一步建议：{nbs['action']}「{target}」（约 {nbs['estimated_minutes']} 分钟）")
    typer.echo("原因：")
    for r in nbs["reasons"]:
        typer.echo(f"  - {r}")


def guard(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except StudyLoopError as e:
            typer.echo(f"错误：{e}", err=True)
            raise typer.Exit(code=1)
    return wrapper
