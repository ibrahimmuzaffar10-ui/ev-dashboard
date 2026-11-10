"""Render Hermes V1 contract to DOCX (editable, with highlights) and PDF (review copy)."""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib, argparse
ap = argparse.ArgumentParser(); ap.add_argument("--content", default="contract_v1_content"); ap.add_argument("--name", default="Hermes V1"); ap.add_argument("--clean", action="store_true"); ap.add_argument("--fill"); ap.add_argument("--out")
ARGS = ap.parse_args()
_c = importlib.import_module(ARGS.content); TITLE, SUBTITLE, SUMMARY, SECTIONS, QUESTIONS = _c.TITLE, _c.SUBTITLE, _c.SUMMARY, _c.SECTIONS, _c.QUESTIONS
CLEAN = ARGS.clean
FILL = __import__("json").load(open(ARGS.fill)) if ARGS.fill else {}
if FILL:  # substitute client values; in "lines" blocks mark them ⟪v⟫ so they are underlined in place
    def _sub(x, mark):
        if isinstance(x, list): return [_sub(i, mark) for i in x]
        def rep(m):
            v = str(FILL.get(m.group(1), "") or "").strip()
            return (f"⟪{v}⟫" if mark else v) if v else m.group(0)
        return re.sub(r"\{\{([^}]+)\}\}", rep, x)
    SECTIONS = [(h, tg, [(k, _sub(c, k == "lines"), t) for (k, c, t) in b]) for (h, tg, b) in SECTIONS]
if CLEAN:  # client-facing view: no review page, no highlights, no notes, blanks instead of {{fields}}
    SECTIONS = [(h, "", [(k, c, "") for (k, c, t) in b if k != "q"]) for (h, tg, b) in SECTIONS]
    def _blank(x):
        if isinstance(x, str): return __import__("re").sub(r"\{\{[^}]+\}\}", "", x) if x.startswith("{{") and x.endswith("}}") else __import__("re").sub(r"\{\{[^}]+\}\}", "______________", x)
        return [_blank(i) for i in x]
    SECTIONS = [(h, tg, [(k, _blank(c), t) for (k, c, t) in b]) for (h, tg, b) in SECTIONS]

OUTDIR = os.path.expanduser("~/Documents/Emanant Visuals/Contracts")
os.makedirs(OUTDIR, exist_ok=True)
BASE = "EMANANT VISUALS - CONTRACT - " + ARGS.name
if ARGS.out: OUTDIR, BASE = os.path.dirname(ARGS.out), os.path.basename(ARGS.out); os.makedirs(OUTDIR, exist_ok=True)

# ---------------- DOCX ----------------
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

HL = {"N": WD_COLOR_INDEX.BRIGHT_GREEN, "C": WD_COLOR_INDEX.YELLOW, "Q": WD_COLOR_INDEX.PINK}

def shade(cell, hexcolor):
    tcPr = cell._tc.get_or_add_tcPr(); s = OxmlElement("w:shd")
    s.set(qn("w:val"), "clear"); s.set(qn("w:color"), "auto"); s.set(qn("w:fill"), hexcolor); tcPr.append(s)

def _bi_runs(par, text, tag):
    text = text.replace("⟪", "").replace("⟫", "")
    for i, part in enumerate(re.split(r"⟦|⟧", text)):
        if not part: continue
        r = par.add_run(part)
        if i % 2 == 1: r.bold = True; r.italic = True
        if tag in HL: r.font.highlight_color = HL[tag]
    return par

def add_runs(par, text, tag, bold_lead=False):
    if bold_lead and ". " in text:
        lead, rest = text.split(". ", 1)
        r = par.add_run(lead + ". "); r.bold = True
        if tag in HL: r.font.highlight_color = HL[tag]
        text = rest
    return _bi_runs(par, text, tag)

doc = Document()
st = doc.styles["Normal"]; st.font.name = "Georgia"; st.font.size = Pt(10.5)
for s in doc.sections:
    s.left_margin = s.right_margin = Inches(0.9); s.top_margin = s.bottom_margin = Inches(0.8)

# Review page (review builds only)
if not CLEAN:
    h = doc.add_paragraph(); h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = h.add_run("REVIEW NOTES — delete this page before using the contract"); r.bold = True; r.font.size = Pt(12); r.font.color.rgb = RGBColor(0xA8, 0x23, 0x1A)
    doc.add_paragraph("Prepared by Hermes for Eman. Color key: green highlight = new clause, yellow = changed wording, pink = decision for Eman. {{curly braces}} are filled in automatically by the dashboard for each client. Not legal advice — a one-time review by a Texas attorney is recommended before regular use.")
    t = doc.add_table(rows=1, cols=2); t.style = "Light Grid Accent 1"
    t.rows[0].cells[0].text = "Type"; t.rows[0].cells[1].text = "What changed"
    for k, v in SUMMARY:
        row = t.add_row().cells; row[0].text = k; row[1].text = v
    doc.add_paragraph()
    p = doc.add_paragraph(); r = p.add_run("Questions for Eman"); r.bold = True
    for q in QUESTIONS:
        doc.add_paragraph(q, style="List Number")
    doc.add_page_break()

# Contract
h = doc.add_paragraph(); h.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = h.add_run(TITLE); r.bold = True; r.font.size = Pt(22); r.font.name = "Georgia"
h2 = doc.add_paragraph(); h2.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = h2.add_run(SUBTITLE); r.italic = True; r.font.size = Pt(12)
for head, tag, blocks in SECTIONS:
    hp = doc.add_paragraph(); hp.paragraph_format.space_before = Pt(10); hp.paragraph_format.space_after = Pt(3)
    hr = hp.add_run(head.upper()); hr.bold = True; hr.font.size = Pt(11); hr.font.color.rgb = RGBColor(0x4A, 0x3B, 0x2C)
    if tag in ("N", "C"):
        lab = hp.add_run("  [NEW]" if tag == "N" else "  [UPDATED]"); lab.font.size = Pt(8); lab.font.highlight_color = HL[tag]
    for kind, content, btag in blocks:
        if kind == "p":
            add_runs(doc.add_paragraph(), content, btag)
        elif kind == "b":
            add_runs(doc.add_paragraph(style="List Bullet"), content, btag, bold_lead=True)
        elif kind == "q":
            qp = doc.add_paragraph(); r = qp.add_run("✎ " + content); r.italic = True; r.font.highlight_color = HL["Q"]
        elif kind == "lines":
            from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER
            for lab, val in content:
                lp = doc.add_paragraph(); lp.paragraph_format.space_after = Pt(4)
                lp.paragraph_format.tab_stops.add_tab_stop(Inches(6.7), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.LINES)
                lr = lp.add_run(lab + ": "); lr.bold = True
                if val:
                    for i, seg in enumerate(re.split(r"⟪|⟫", val.replace("______________", "            "))):
                        if seg: rr = lp.add_run(seg); rr.underline = (i % 2 == 1)
                    lp.add_run(" ")
                lp.add_run("\t")
        elif kind == "tbl":
            cols = len(content[0]); tb = doc.add_table(rows=0, cols=cols); tb.style = "Table Grid"
            for i, row in enumerate(content):
                cells = tb.add_row().cells
                for j, val in enumerate(row):
                    cells[j].text = val
                    for pr in cells[j].paragraphs:
                        for rr in pr.runs:
                            rr.font.size = Pt(10)
                            if (cols == 2 and j == 0) or (cols > 2 and i == 0): rr.bold = True
                    if cols == 2 and j == 0: shade(cells[j], "F3EFEA")
                    if cols > 2 and i == 0: shade(cells[j], "F3EFEA")
            doc.add_paragraph()
docx_path = os.path.join(OUTDIR, BASE + ".docx"); doc.save(docx_path)

# ---------------- PDF ----------------
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, ListFlowable, ListItem, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

ss = getSampleStyleSheet()
BODY = ParagraphStyle("b", parent=ss["Normal"], fontName="Times-Roman", fontSize=10.3, leading=13.6, spaceAfter=5)
H = ParagraphStyle("h", parent=BODY, fontName="Times-Bold", fontSize=11.5, textColor=colors.HexColor("#4A3B2C"), spaceBefore=9, spaceAfter=3)
T = ParagraphStyle("t", parent=BODY, fontName="Times-Bold", fontSize=24, alignment=1, spaceAfter=2, leading=28)
ST = ParagraphStyle("st", parent=BODY, fontName="Times-Italic", fontSize=12.5, alignment=1, spaceAfter=10)
SM = ParagraphStyle("sm", parent=BODY, fontSize=9.5, leading=12)
BG = {"N": "#D6F5DD", "C": "#FFF1B8", "Q": "#FBD3CF"}

from reportlab.platypus import Flowable
from reportlab.pdfbase.pdfmetrics import stringWidth
class FillLine(Flowable):
    """Label: text ____ text ____ → line to the right margin. Words are never underlined; blanks hug the words."""
    W_TOTAL = 6.7 * inch; FS = 10.3; BLANK = 1.1 * inch
    def __init__(self, label, value): super().__init__(); self.label, self.value = label, value
    def wrap(self, aw, ah): return (self.W_TOTAL, 22)
    def draw(self):
        c = self.canv; y = 5; x = 0
        c.setFont("Times-Bold", self.FS); lab = self.label + ":"; c.drawString(0, y, lab); x = stringWidth(lab, "Times-Bold", self.FS) + 6
        parts = re.split(r"(\{\{[^}]+\}\}|______________|⟪[^⟫]*⟫)", self.value or "")
        c.setFont("Times-Roman", self.FS); c.setStrokeColor(colors.HexColor("#555555")); c.setLineWidth(0.6)
        texts = [p for p in parts if p and not (p.startswith("{{") or p.startswith("___"))]
        for p in parts:
            if not p: continue
            if p.startswith("⟪"):
                t = p[1:-1]; w = max(stringWidth(t, "Times-Roman", self.FS) + 8, self.BLANK)
                if p == [q for q in parts if q][-1]: w = max(w, self.W_TOTAL - x)
                c.drawString(x + 3, y, t); c.line(x, y - 2, x + w, y - 2); x += w + 4; continue
            if p.startswith("{{") or p.startswith("___"):
                c.line(x, y - 2, x + self.BLANK, y - 2); x += self.BLANK + 4
            else:
                c.drawString(x, y, p.strip() and p or p); x += stringWidth(p, "Times-Roman", self.FS) + 2
        last = (self.value or "").rstrip()
        if x < self.W_TOTAL - 10 and not (last.endswith("}}") or last.endswith("___") or last.endswith("⟫")):
            c.line(x + 2, y - 2, self.W_TOTAL, y - 2)

def esc(s): return s.replace("⟪", "").replace("⟫", "").replace("☐", "[  ]").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
def para(text, tag, style=BODY, bold_lead=False):
    t = esc(text)
    if bold_lead and ". " in t:
        lead, rest = t.split(". ", 1); t = f"<b>{lead}.</b> {rest}"
    t = re.sub(r"(\{\{[^}]+\}\})", r'<font color="#6d4aff">\1</font>', t)
    t = re.sub(r"⟦(.*?)⟧", r"<b><i>\1</i></b>", t)
    if tag in BG: t = f'<span backColor="{BG[tag]}">{t}</span>'
    return Paragraph(t, style)

story = [] if CLEAN else [Paragraph('<font color="#a8231a"><b>REVIEW NOTES</b></font> — this page is for Eman only', H),
         Paragraph("Color key: <span backColor='#D6F5DD'>green = new</span>, <span backColor='#FFF1B8'>yellow = changed</span>, <span backColor='#FBD3CF'>pink = decision for Eman</span>. <font color='#6d4aff'>{{purple}}</font> fields are filled automatically per client by the dashboard. Not legal advice; a one-time review by a Texas attorney is recommended.", BODY),
         Table([[Paragraph("<b>Type</b>", SM), Paragraph("<b>What changed</b>", SM)]] + [[Paragraph(k, SM), Paragraph(esc(v), SM)] for k, v in SUMMARY],
               colWidths=[0.8 * inch, 5.9 * inch], style=TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d8d2c8")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3EFEA")), ("VALIGN", (0, 0), (-1, -1), "TOP")])),
         Spacer(1, 8), Paragraph("<b>Questions for Eman</b>", BODY),
         ListFlowable([ListItem(Paragraph(esc(q), BODY)) for q in QUESTIONS], bulletType="1"), PageBreak()]
story += [Paragraph(TITLE, T), Paragraph(SUBTITLE, ST)]
for head, tag, blocks in SECTIONS:
    lab = {"N": " <font size=7 backColor='#D6F5DD'> NEW </font>", "C": " <font size=7 backColor='#FFF1B8'> UPDATED </font>"}.get(tag, "")
    flow = [Paragraph(esc(head.upper()) + lab, H)]
    for kind, content, btag in blocks:
        if kind == "p": flow.append(para(content, btag))
        elif kind == "b": flow.append(ListFlowable([ListItem(para(content, btag, bold_lead=True), leftIndent=12)], bulletType="bullet", start="•", leftIndent=12))
        elif kind == "q": flow.append(para("✎ " + content, "Q"))
        elif kind == "lines":
            for l, v in content:
                plain = re.sub(r"⟪|⟫", "", v or "")
                if "⟪" in (v or "") and stringWidth(l + ": " + plain, "Times-Roman", 10.3) > 6.4 * inch:
                    flow.append(Paragraph(f"<b>{esc(l)}:</b> <u>" + esc(v) + "</u>", BODY))
                else:
                    flow.append(FillLine(l, v))
            flow.append(Spacer(1, 6))
        elif kind == "lines_old":
            data = [[Paragraph(f"<b>{esc(l)}:</b>", BODY), para(v.replace("______________", "\u00a0" * 16), "", BODY)] for l, v in content]
            lt = Table(data, colWidths=[2.2 * inch, 4.5 * inch])
            lt.setStyle(TableStyle([("LINEBELOW", (1, 0), (1, -1), 0.6, colors.HexColor("#555555")), ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                                    ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 1), ("LEFTPADDING", (0, 0), (0, -1), 0)]))
            flow += [lt, Spacer(1, 6)]
        elif kind == "tbl":
            cols = len(content[0])
            data = [[para(c, "", SM) for c in row] for row in content]
            widths = [2.2 * inch, 4.5 * inch] if cols == 2 else ([1.4 * inch, 4.4 * inch, 0.9 * inch] if content[0][0] == "Option" else [6.7 * inch / cols] * cols)
            tsty = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d8d2c8")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]
            tsty.append(("BACKGROUND", (0, 0), (0, -1) if cols == 2 else (-1, 0), colors.HexColor("#F3EFEA")))
            if btag in BG: tsty.append(("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor({"N": "#7cc68f", "C": "#e5c84d"}[btag])))
            rh = [22 if all(not str(c).strip() for c in row) else None for row in content]
            if "signature" in str(content[0]).lower(): rh = [None if (i % 2 == 0) else 34 for i in range(len(content))]
            flow += [Table(data, colWidths=widths, rowHeights=rh, style=TableStyle(tsty)), Spacer(1, 6)]
    # short sections never split; long ones keep heading + first block together and break only between blocks
    _W, _H = letter[0] - 1.8 * inch, letter[1] - 1.6 * inch
    from reportlab.pdfgen.canvas import Canvas as _C; import io as _io
    _cv = _C(_io.BytesIO()); _h = sum(f.wrapOn(_cv, _W, _H)[1] for f in flow)
    if _h <= 0.42 * _H: story.append(KeepTogether(flow))
    else:
        story.append(KeepTogether(flow[:3])); story += flow[3:]

def footer(c, d):
    c.saveState(); c.setFont("Times-Italic", 8); c.setFillColor(colors.HexColor("#8a8a8a"))
    c.drawString(0.9 * inch, 0.5 * inch, "Emanant Visuals · Photography & Creative Services Agreement" + ("" if CLEAN else " · " + ARGS.name + " (draft for review)"))
    c.drawRightString(7.6 * inch, 0.5 * inch, f"Page {d.page}"); c.restoreState()
pdf_path = os.path.join(OUTDIR, BASE + (".pdf" if CLEAN else " (review).pdf"))
SimpleDocTemplate(pdf_path, pagesize=letter, leftMargin=0.9 * inch, rightMargin=0.9 * inch, topMargin=0.8 * inch, bottomMargin=0.8 * inch,
                  title="Emanant Visuals Contract — Hermes V1", author="Hermes for Emanant Visuals").build(story, onFirstPage=footer, onLaterPages=footer)
print(docx_path); print(pdf_path)


# keep a copy the dashboard can serve (launchd can't read files in ~/Documents it didn't create)
if ARGS.name == "VFinal" and not ARGS.out:
    import shutil as _sh, os as _os
    _d = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "served")
    _os.makedirs(_d, exist_ok=True)
    _k = "contract"
    for _ext in (".pdf", ".docx"):
        _src = _os.path.join(OUTDIR, BASE + _ext)
        if _os.path.exists(_src): _sh.copy(_src, _os.path.join(_d, _k + _ext))
