#!/usr/bin/env python3
"""Render the exam markdown files to clean CJK PDFs with reportlab."""
import re, sys, html
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable, PageBreak)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT

# ---- register CJK fonts (Heiti Light body, Heiti Medium bold/heading) ----
F = "/Users/td_xu/Desktop/SKill/study-loop/tmp/fonts/"
pdfmetrics.registerFont(TTFont("Body", F+"STHeitiLight.ttc", subfontIndex=0))
pdfmetrics.registerFont(TTFont("HeitiM", F+"STHeitiMedium.ttc", subfontIndex=0))
from reportlab.pdfbase.pdfmetrics import registerFontFamily
registerFontFamily("Body", normal="Body", bold="HeitiM", italic="Body", boldItalic="HeitiM")

SS = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=SS["Title"], fontName="HeitiM", fontSize=16, leading=22, spaceAfter=6, textColor=colors.HexColor("#1a1a1a"))
H2 = ParagraphStyle("H2", fontName="HeitiM", fontSize=12.5, leading=18, spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#0b5394"))
H3 = ParagraphStyle("H3", fontName="HeitiM", fontSize=11, leading=16, spaceBefore=6, spaceAfter=3, textColor=colors.HexColor("#333333"))
BODY = ParagraphStyle("BODY", fontName="Body", fontSize=10.5, leading=16.5, alignment=TA_LEFT, spaceAfter=3)
OPT = ParagraphStyle("OPT", fontName="Body", fontSize=10.5, leading=15, leftIndent=14, spaceAfter=1)
QUOTE = ParagraphStyle("QUOTE", fontName="Body", fontSize=10, leading=15, leftIndent=16, textColor=colors.HexColor("#444444"), spaceAfter=3)

def inline(t):
    t = t.replace("\\_", "_")          # un-escape underscores (blank-fill lines)
    t = html.escape(t)                 # single escape: & < > "
    parts = t.split("**")              # toggle bold on each ** pair
    if len(parts) > 1:
        out = []
        for i, p in enumerate(parts):
            if i % 2 == 1:
                out += ["<b>", p, "</b>"]
            else:
                out.append(p)
        t = "".join(out)
    return t

def parse(md):
    flows = []
    lines = md.split("\n")
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].rstrip("\n")
        s = line.strip()
        if s == "" :
            i += 1; continue
        if s == "---":
            flows.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#bbbbbb"), spaceBefore=4, spaceAfter=4)); i+=1; continue
        if s.startswith("# "):
            flows.append(Paragraph(s[2:].strip(), H1)); i+=1; continue
        if s.startswith("## "):
            flows.append(Paragraph(s[3:].strip(), H2)); i+=1; continue
        if s.startswith("### "):
            flows.append(Paragraph(s[4:].strip(), H3)); i+=1; continue
        if s.startswith("> "):
            blk=[]
            while i<n and lines[i].strip().startswith(">"):
                blk.append(lines[i].strip()[1:].strip()); i+=1
            flows.append(Paragraph("<br/>".join(inline(x) for x in blk), QUOTE)); continue
        # table block
        if s.startswith("|"):
            rows=[]
            while i<n and lines[i].strip().startswith("|"):
                cells=[c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(cells); i+=1
            # drop separator row (---)
            data=[[Paragraph(inline(c), BODY) for c in r] for r in rows if not set(c.replace("-","").replace(":","") for c in r)=={""}]
            if data:
                t=Table(data, hAlign="LEFT", colWidths=[None]*len(data[0]))
                t.setStyle(TableStyle([
                    ("FONT",(0,0),(-1,-1),"Body",9.5),
                    ("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#cccccc")),
                    ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#eef3f8")),
                    ("VALIGN",(0,0),(-1,-1),"TOP"),
                    ("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),
                    ("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3),
                ]))
                # set column widths: first col narrower
                ncols=len(data[0])
                if ncols>=3:
                    widths=[14*mm]+[(168-14)/ (ncols-1) *mm]*(ncols-1)
                    t._argW=widths
                flows.append(t); flows.append(Spacer(1,4))
            continue
        # option lines start with full-width space or " A." style
        if re.match(r"^[　\s]*[A-E][．.、]", s):
            flows.append(Paragraph(inline(s), OPT)); i+=1; continue
        flows.append(Paragraph(inline(s), BODY)); i+=1
    return flows

def build(md_path, pdf_path):
    md=open(md_path,encoding="utf-8").read()
    doc=SimpleDocTemplate(pdf_path, pagesize=A4,
        leftMargin=20*mm,rightMargin=20*mm,topMargin=18*mm,bottomMargin=18*mm,
        title=pdf_path.split("/")[-1])
    doc.build(parse(md))
    print("wrote", pdf_path)

if __name__=="__main__":
    base="/Users/td_xu/courses/毛中特/output/"
    build(base+"毛中特期末模拟卷.md", base+"毛中特期末模拟卷.pdf")
    build(base+"毛中特期末模拟卷-答案解析.md", base+"毛中特期末模拟卷-答案解析.pdf")
