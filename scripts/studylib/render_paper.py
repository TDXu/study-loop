from __future__ import annotations

import html as _html
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (HRFlowable, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

BODY_FONT = "Body"
BOLD_FONT = "HeitiM"
_REGISTERED_KEY: str | None = None  # guards repeated registration in one process


def _register_fonts(fonts_dir: Path | None) -> None:
    """Register CJK fonts. Prefer Heiti .ttc from fonts_dir; else fall back to
    reportlab's built-in CID font STSong-Light (no font files needed). Sets the
    module-level BODY_FONT/BOLD_FONT so styles resolve correctly either way."""
    global BODY_FONT, BOLD_FONT, _REGISTERED_KEY
    fonts_dir = Path(fonts_dir) if fonts_dir else None
    use_heiti = bool(fonts_dir and (fonts_dir / "STHeitiLight.ttc").exists()
                     and (fonts_dir / "STHeitiMedium.ttc").exists())
    key = f"heiti:{fonts_dir}" if use_heiti else "cid"
    if _REGISTERED_KEY == key:
        return  # already registered with this config in this process
    if use_heiti:
        pdfmetrics.registerFont(TTFont("Body", str(fonts_dir / "STHeitiLight.ttc"), subfontIndex=0))
        pdfmetrics.registerFont(TTFont("HeitiM", str(fonts_dir / "STHeitiMedium.ttc"), subfontIndex=0))
        BODY_FONT, BOLD_FONT = "Body", "HeitiM"
    else:
        # UnicodeCIDFont registers under its face name; reuse that name for both.
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        BODY_FONT = BOLD_FONT = "STSong-Light"
    registerFontFamily(BODY_FONT, normal=BODY_FONT, bold=BOLD_FONT,
                       italic=BODY_FONT, boldItalic=BOLD_FONT)
    _REGISTERED_KEY = key


def _styles():
    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=ss["Title"], fontName=BOLD_FONT, fontSize=16,
                             leading=22, spaceAfter=6, textColor=colors.HexColor("#1a1a1a")),
        "body": ParagraphStyle("body", fontName=BODY_FONT, fontSize=10.5, leading=16.5,
                               alignment=TA_LEFT, spaceAfter=3),
        "opt": ParagraphStyle("opt", fontName=BODY_FONT, fontSize=10.5, leading=15,
                              leftIndent=14, spaceAfter=1),
        "quote": ParagraphStyle("quote", fontName=BODY_FONT, fontSize=10, leading=15,
                                leftIndent=16, textColor=colors.HexColor("#444444"), spaceAfter=3),
    }


def _inline(t: str) -> str:
    t = t.replace("\\_", "_")
    t = _html.escape(t)
    parts = t.split("**")
    if len(parts) > 1:
        out = []
        for i, p in enumerate(parts):
            out += ["<b>", p, "</b>"] if i % 2 else [p]
        t = "".join(out)
    return t


def manifest_to_markdown(manifest: dict, variant: str) -> str:
    if variant not in ("questions", "answers"):
        raise ValueError(f"unknown variant: {variant}")
    meta = manifest["meta"]
    lines = [f"# {meta['course_name']} · 模拟卷",
             f"> {meta['mode']} 模式 · {len(manifest['questions'])} 题 · 生成于 {meta['generated_at']}", ""]
    for i, q in enumerate(manifest["questions"], 1):
        kcs = " · ".join(q.get("kc_labels") or q.get("kc_ids", []))
        lines.append(f"### 第 {i} 题　{kcs}")
        lines.append(q.get("stem", ""))
        if variant == "answers":
            lines += ["", f"**答案：{q.get('answer', '')}**", f"> 解析：{q.get('solution', '')}"]
        lines.append("")
    return "\n".join(lines)


def _parse(md: str, st: dict) -> list:
    import re
    flows, lines, i, n = [], md.split("\n"), 0, len(md.split("\n"))
    while i < n:
        line = lines[i].rstrip("\n")
        s = line.strip()
        if s == "":
            i += 1
            continue
        if s == "---":
            flows.append(HRFlowable(width="100%", thickness=0.6,
                                    color=colors.HexColor("#bbbbbb"), spaceBefore=4, spaceAfter=4))
            i += 1
            continue
        if s.startswith("# "):
            flows.append(Paragraph(_inline(s[2:].strip()), st["h1"])); i += 1; continue
        if s.startswith("### "):
            flows.append(Paragraph(_inline(s[4:].strip()),
                                   ParagraphStyle("h3", parent=st["body"], fontName=BOLD_FONT,
                                                  textColor=colors.HexColor("#0b5394"), spaceBefore=6)))
            i += 1; continue
        if s.startswith("> "):
            blk = []
            while i < n and lines[i].strip().startswith(">"):
                blk.append(lines[i].strip()[1:].strip()); i += 1
            flows.append(Paragraph("<br/>".join(_inline(x) for x in blk), st["quote"])); continue
        if re.match(r"^[　\s]*[A-H][．.、]", s):
            flows.append(Paragraph(_inline(s), st["opt"])); i += 1; continue
        flows.append(Paragraph(_inline(s), st["body"])); i += 1
    return flows


def markdown_to_pdf(md: str, pdf_path: Path, fonts_dir: Path | None = None) -> Path:
    _register_fonts(fonts_dir)
    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title=Path(pdf_path).name)
    doc.build(_parse(md, _styles()))
    return Path(pdf_path)
