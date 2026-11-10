"""Client To-Do Questionnaire V1.1 — renders DOCX + PDF (clean, client-facing).
Sent after the contract is signed. Section A is pre-filled by Emanant Visuals from the signed agreement."""
import os, re
OT_RATE = os.environ.get("EV_OVERTIME_RATE", "the agreed overtime rate")  # e.g. "$X per hour", kept out of git
OUTDIR = os.path.expanduser("~/Documents/Emanant Visuals/Contracts")
import argparse, json
_ap = argparse.ArgumentParser(); _ap.add_argument("--fill"); _ap.add_argument("--out"); _A = _ap.parse_args()
FILL = json.load(open(_A.fill)) if _A.fill else {}
NAME = "EMANANT VISUALS - Client To-Do Questionnaire - VFinal"
if _A.out: OUTDIR, NAME = os.path.dirname(_A.out), os.path.basename(_A.out)

# blocks: ("h", title, note) | ("p", text) | ("f", label) field line | ("t", headers, n_rows) table | ("pre", [(label, value)]) prefilled
Q = [
 ("p", "Thank you for booking Emanant Visuals! This questionnaire helps us build your day-of timeline, so every moment is captured and your coverage runs smoothly and on time. Please complete and return it by: {{questionnaire_due}} (four weeks before your first event)."),
 ("h", "A. Your Booking", "Pre-filled by Emanant Visuals from your signed agreement"),
 ("pre", [("Client name(s)", "{{client_names}}"), ("Package", "{{package_name}}"), ("Privacy package", "{{privacy_option}}"), ("Photographers", "{{photographers}}")]),
 ("pret", ["Day", "Event", "Date", "Contracted start", "Contracted end", "Hours"], "{{coverage_rows}}", 3),
 ("p", "These details come from your signed agreement. To change coverage hours or your privacy package, please contact Eman for a written update. Coverage beyond the contracted hours is billed at " + OT_RATE + ", as stated in your agreement."),
 ("h", "B. Contact & Communication", ""),
 ("t", ["", "Name", "Phone", "Email"], [["Partner 1"], ["Partner 2"]]),
 ("f", "Best phone number to reach you on the event day(s)"),
 ("t", ["Day-of contact(s)", "Phone", "Role (e.g. sibling, cousin)"], 2),
 ("p", "Your day-of contact knows the itinerary, can answer questions on the day, and helps gather family members for photos."),
 ("t", ["Planner / coordinator", "Phone", "Email"], 1),
 ("f", "If you are unavailable, who should Eman communicate with directly?"),
 ("f", "Emergency contact (name + phone)"),
 ("h", "C. Events & Locations", "List every event day (e.g. mehndi, nikkah, baraat, walima, rukhsati, reception)"),
 ("t", ["Event", "Date", "Venue name & full address", "Start", "End"], 4),
 ("f", "Getting ready: time, address, and photos for one or both partners?"),
 ("f", "Parking / load-in instructions for each venue"),
 ("f", "Will any part of the event be outdoors? (Where and when?)"),
 ("h", "D. Day-of Timeline", "Hour by hour, so we stay on schedule within your contracted coverage"),
 ("t", ["Time", "What’s happening", "Where"], 10),
 ("f", "Are you doing a first look? (If yes, where and when?)"),
 ("f", "Ceremony time and expected length"),
 ("f", "Key reception moments (entrance, first dance, speeches, cake cutting, exit, etc.)"),
 ("f", "Do you plan a grand exit? (sparklers, confetti, etc.)"),
 ("h", "E. People & Family Photos", ""),
 ("f", "Bridesmaids / groomsmen (how many, and names)"),
 ("f", "Partner 1’s immediate family"),
 ("f", "Partner 2’s immediate family"),
 ("t", ["Family photo grouping (in order)", "Names"], 8),
 ("f", "Who will help gather family members quickly? (usually the day-of contact)"),
 ("f", "Any sensitive family dynamics we should be aware of? (divorces, conflicts, etc.)"),
 ("f", "Any guests who should not be photographed?"),
 ("h", "F. Vendors & Venue", "Names and Instagram handles so we can coordinate and credit your vendors"),
 ("t", ["Vendor", "Name / company", "Instagram handle"], [["Planner"], ["Venue"], ["Decor / florist"], ["Hair & makeup"], ["Henna"], ["Catering"], ["DJ / entertainment"], ["Videographer / content creator"], ["Other photographers"], ["Food / coffee carts"], ["Other"]]),
 ("f", "Any venue restrictions on photography? (flash, movement, areas, etc.)"),
 ("f", "What is the lighting like for your ceremony / reception?"),
 ("f", "Will there be lasers or laser lighting at any point (DJ, stage, dance floor)? If yes, which event, roughly when, and the DJ\u2019s contact. (Required: see the Lasers section of your contract.)"),
 ("f", "Any specific spots at the venue where you want photos?"),
 ("h", "G. Moments, Details & Traditions", ""),
 ("f", "Special traditions, cultural elements or rasams planned"),
 ("f", "Special entertainment or planned surprises"),
 ("f", "Meaningful details you want documented"),
 ("h", "H. Style & Must-Have Shots", ""),
 ("f", "How would you describe your ideal photo style? (light & airy, dark & moody, candid, editorial, etc.)"),
 ("f", "Specific photos you must have (poses, friend groups, details)"),
 ("f", "Inspiration photos or Pinterest board link"),
 ("p", "Thank you! Eman will review your answers and reach out if anything needs clarifying before your timeline call."),
]

def blank(s): return re.sub(r"\{\{([^}]+)\}\}", lambda m: str(FILL.get(m.group(1), "") or "______________"), s)
COV = FILL.get("coverage_rows") or []

# ---------- DOCX ----------
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
def shade(cell, hx):
    p = cell._tc.get_or_add_tcPr(); s = OxmlElement("w:shd"); s.set(qn("w:val"), "clear"); s.set(qn("w:color"), "auto"); s.set(qn("w:fill"), hx); p.append(s)
doc = Document(); st = doc.styles["Normal"]; st.font.name = "Georgia"; st.font.size = Pt(10.5)
for s in doc.sections: s.left_margin = s.right_margin = Inches(0.9); s.top_margin = s.bottom_margin = Inches(0.8)
h = doc.add_paragraph(); h.alignment = WD_ALIGN_PARAGRAPH.CENTER; r = h.add_run("EMANANT VISUALS"); r.bold = True; r.font.size = Pt(22)
h = doc.add_paragraph(); h.alignment = WD_ALIGN_PARAGRAPH.CENTER; r = h.add_run("Client To-Do Questionnaire"); r.italic = True; r.font.size = Pt(12)
def table(headers, rows):
    tb = doc.add_table(rows=1, cols=len(headers)); tb.style = "Table Grid"
    for j, x in enumerate(headers):
        c = tb.rows[0].cells[j]; c.text = x; shade(c, "F3EFEA")
        for rr in c.paragraphs[0].runs: rr.bold = True; rr.font.size = Pt(9.5)
    for row in rows:
        cells = tb.add_row().cells
        for j in range(len(headers)):
            cells[j].text = blank(row[j]) if j < len(row) else ""
            if j < len(row) and row[j]:
                for rr in cells[j].paragraphs[0].runs: rr.font.size = Pt(9.5); rr.bold = True
    doc.add_paragraph()
for b in Q:
    k = b[0]
    if k == "h":
        p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(10); r = p.add_run(b[1].upper()); r.bold = True; r.font.color.rgb = RGBColor(0x4A, 0x3B, 0x2C)
        if b[2]: n = p.add_run("  — " + b[2]); n.italic = True; n.font.size = Pt(9)
    elif k == "p": doc.add_paragraph(blank(b[1]))
    elif k == "f":
        p = doc.add_paragraph(); r = p.add_run(b[1]); r.bold = True
        doc.add_paragraph("_" * 86)
    elif k == "pre":
        tb = doc.add_table(rows=0, cols=2); tb.style = "Table Grid"
        for lab, val in b[1]:
            c = tb.add_row().cells; c[0].text = lab; shade(c[0], "F3EFEA"); c[1].text = blank(val)
        doc.add_paragraph()
    elif k == "pret": table(b[1], (COV + [[""] * len(b[1])] * b[3])[:max(b[3], len(COV))])
    elif k == "t": table(b[1], b[2] if isinstance(b[2], list) else [[""]] * b[2])
os.makedirs(OUTDIR, exist_ok=True); dp = os.path.join(OUTDIR, NAME + ".docx"); doc.save(dp)

# ---------- PDF ----------
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
ss = getSampleStyleSheet()
BODY = ParagraphStyle("b", parent=ss["Normal"], fontName="Times-Roman", fontSize=10.3, leading=13.5, spaceAfter=4)
LAB = ParagraphStyle("l", parent=BODY, fontName="Times-Bold", spaceAfter=1)
H = ParagraphStyle("h", parent=BODY, fontName="Times-Bold", fontSize=11.5, textColor=colors.HexColor("#4A3B2C"), spaceBefore=10, spaceAfter=4)
SM = ParagraphStyle("s", parent=BODY, fontSize=9.3, leading=11.5)
T = ParagraphStyle("t", parent=BODY, fontName="Times-Bold", fontSize=24, alignment=1, leading=28)
ST = ParagraphStyle("st", parent=BODY, fontName="Times-Italic", fontSize=12.5, alignment=1, spaceAfter=10)
W = 6.7 * inch
GRID = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d8d2c8")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
def ptable(headers, rows, heights=20):
    data = [[Paragraph(f"<b>{h}</b>", SM) for h in headers]] + [[Paragraph(f"<b>{blank(r[j])}</b>" if j < len(r) and r[j] else "", SM) for j in range(len(headers))] for r in rows]
    t = Table(data, colWidths=[W / len(headers)] * len(headers), rowHeights=[None] + [heights] * len(rows))
    t.setStyle(TableStyle(GRID + [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3EFEA"))])); return t
story = [Paragraph("EMANANT VISUALS", T), Paragraph("Client To-Do Questionnaire", ST)]
for b in Q:
    k = b[0]
    if k == "h": story.append(Paragraph(b[1].upper() + (f" <font size=8.5 color='#8a8a8a'><i>— {b[2]}</i></font>" if b[2] else ""), H))
    elif k == "p": story.append(Paragraph(blank(b[1]), BODY))
    elif k == "f":
        line = Table([[""]], colWidths=[W], rowHeights=[24]); line.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#b9b2a6"))]))
        story.append(KeepTogether([Paragraph(b[1], LAB), line, Spacer(1, 6)]))
    elif k == "pre":
        t = Table([[Paragraph(f"<b>{l}</b>", SM), Paragraph(blank(v), SM)] for l, v in b[1]], colWidths=[1.8 * inch, W - 1.8 * inch])
        t.setStyle(TableStyle(GRID + [("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3EFEA"))])); story += [t, Spacer(1, 6)]
    elif k == "pret": story += [ptable(b[1], (COV + [[""] * len(b[1])] * b[3])[:max(b[3], len(COV))]), Spacer(1, 6)]
    elif k == "t": story += [KeepTogether([ptable(b[1], b[2] if isinstance(b[2], list) else [[""]] * b[2])]), Spacer(1, 8)]
def footer(c, d):
    c.saveState(); c.setFont("Times-Italic", 8); c.setFillColor(colors.HexColor("#8a8a8a"))
    c.drawString(0.9 * inch, 0.5 * inch, "Emanant Visuals · Client To-Do Questionnaire"); c.drawRightString(7.6 * inch, 0.5 * inch, f"Page {d.page}"); c.restoreState()
pp = os.path.join(OUTDIR, NAME + ".pdf")
SimpleDocTemplate(pp, pagesize=letter, leftMargin=0.9 * inch, rightMargin=0.9 * inch, topMargin=0.8 * inch, bottomMargin=0.8 * inch, title="Emanant Visuals — Client To-Do Questionnaire").build(story, onFirstPage=footer, onLaterPages=footer)
print(dp); print(pp)


# keep a copy the dashboard can serve (launchd can't read files in ~/Documents it didn't create)
if not _A.out:
    import shutil as _sh, os as _os
    _d = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "served")
    _os.makedirs(_d, exist_ok=True)
    _k = "questionnaire"
    for _ext in (".pdf", ".docx"):
        _src = _os.path.join(OUTDIR, NAME + _ext)
        if _os.path.exists(_src): _sh.copy(_src, _os.path.join(_d, _k + _ext))
