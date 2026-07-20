from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from jinja2 import Template

TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "templates" / "quiz.html.j2"

_OPT_RE = re.compile(r"^\s*([A-Ha-hＡ-Ｈａ-ｈ])[．.、)]\s*(.*)$")


def parse_options(stem: str) -> tuple[str, list[tuple[str, str]]]:
    lines = stem.splitlines()
    body: list[str] = []
    opts: list[list[str]] = []  # each: [letter, text]
    in_opts = False
    for ln in lines:
        m = _OPT_RE.match(ln)
        if m:
            in_opts = True
            letter = unicodedata.normalize("NFKC", m.group(1)).upper()
            opts.append([letter, m.group(2).strip()])
        elif not in_opts:
            body.append(ln)
        else:
            opts[-1][1] = (opts[-1][1] + " " + ln.strip()).strip()
    return "\n".join(body).strip(), [(o[0], o[1]) for o in opts]


def _question_for_render(q: dict) -> dict:
    body, opts = parse_options(q.get("stem", ""))
    ans = q.get("answer", "") or ""
    letters = sorted({unicodedata.normalize("NFKC", ch).upper() for ch in ans if ch.strip()})
    return {
        "stem": body,
        "options": [{"letter": l, "text": t} for l, t in opts],
        "answer": "".join(letters),
        "answer_letters": letters,
        "multi": len(letters) > 1,
        "solution": q.get("solution", ""),
        "kc_labels": q.get("kc_labels") or q.get("kc_ids", []),
    }


def render_quiz_html(manifest: dict, reveal_default: bool = True) -> str:
    tpl = Template(TEMPLATE_PATH.read_text(encoding="utf-8"))
    view = {
        "meta": manifest["meta"],
        "questions": [_question_for_render(q) for q in manifest["questions"]],
    }
    return tpl.render(m=view, reveal_default=("on" if reveal_default else "off"))
