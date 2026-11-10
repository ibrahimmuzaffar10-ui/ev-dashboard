"""Emanant Visuals live dashboard server (stdlib only).

Run:  python3 server.py            -> http://localhost:8787
Data: tracker_data.json (same folder). Every change is backed up and logged.
"""
import json, os, shutil, datetime, threading, re, smtplib, imaplib, subprocess, time
from email.message import EmailMessage
from email.utils import make_msgid, formatdate
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import html as _html, tempfile
import evenv
import db, evtime

HERE = os.path.dirname(os.path.abspath(__file__))
# Data lives outside the repo (EV_DATA_DIR); the repo holds code only.
DATA_DIR = os.path.expanduser(os.environ.get("EV_DATA_DIR", HERE))
DATA_PATH = os.path.join(DATA_DIR, "tracker_data.json")
TEMPLATE = os.path.join(HERE, "dashboard_template.html")
BACKUPS = os.path.join(DATA_DIR, "backups")
PAY_PATH = os.path.join(DATA_DIR, "payments.json")
PORT = int(os.environ.get("EV_PORT", "8787"))
HOST = os.environ.get("EV_HOST", "127.0.0.1")
LOCK = threading.Lock()
OWN_EMAIL = evenv.need("EV_ICLOUD_LOGIN")
FROM_EMAIL = evenv.need("EV_FROM_EMAIL")  # business address (iCloud+ custom domain); login stays the Apple ID email

def icloud_pw():
    return subprocess.run(["security", "find-generic-password", "-s", "hermes-icloud", "-w"], capture_output=True, text=True, timeout=20).stdout.strip()

def send_mail(to, subject, body, in_reply_to=None, attachments=()):
    if db.CLOUD:  # cloud mode never sends mail itself: the Mac outbox does (Phase 4c)
        raise RuntimeError("email sending is not available in cloud mode yet")
    msg = EmailMessage()
    msg["From"] = f"Eman | Emanant Visuals <{FROM_EMAIL}>"; msg["To"] = to; msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True); msg["Message-ID"] = make_msgid(domain="emanantvisuals.com")
    if in_reply_to:
        ref = in_reply_to if in_reply_to.startswith("<") else f"<{in_reply_to}>"
        msg["In-Reply-To"] = ref; msg["References"] = ref
    msg.set_content(body)
    for ap in attachments or ():
        with open(ap, "rb") as fh:
            data = fh.read()
        sub = "pdf" if ap.endswith(".pdf") else "vnd.openxmlformats-officedocument.wordprocessingml.document"
        msg.add_attachment(data, maintype="application", subtype=sub, filename=os.path.basename(ap))
    pw = icloud_pw()
    with smtplib.SMTP("smtp.mail.me.com", 587, timeout=30) as s:
        s.starttls(); s.login(OWN_EMAIL, pw); s.send_message(msg)
    try:  # keep a copy in Sent so Eman sees it in Mail
        im = imaplib.IMAP4_SSL("imap.mail.me.com"); im.login(OWN_EMAIL, pw)
        im.append('"Sent Messages"', "\\Seen", imaplib.Time2Internaldate(time.time()), msg.as_bytes()); im.logout()
    except Exception:
        pass
    return msg["Message-ID"]

# ---------------- contracts ----------------
VENV_PY = os.path.expanduser(os.environ.get("EV_PYTHON", "~/.hermes/venvs/ev/bin/python"))
CDIR = os.path.join(HERE, "contracts")
EVDOCS = os.path.expanduser(os.environ.get("EV_DOCS_DIR", "~/Documents/Emanant Visuals"))
# Contract wording (prices, payment details) is NOT in git: it lives in EV_CONTRACT_CONTENT_DIR.
CONTENT_DIR = os.path.expanduser(os.environ.get("EV_CONTRACT_CONTENT_DIR", ""))
SERVED_DIR = os.path.expanduser(os.environ.get("EV_SERVED_DIR", os.path.join(CDIR, "served")))

def privacy_options_html():
    opts = evenv.as_list("EV_PRIVACY_OPTIONS") or ["Standard usage"]
    return "".join(f"<option>{_html.escape(o)}</option>" for o in opts)
DRAFTS, SIGNED, QDIR = (os.path.join(EVDOCS, x) for x in ("Contract Drafts", "Signed Contracts", "Questionnaires"))
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
def pretty(dt):
    try: y, m, dd = map(int, str(dt)[:10].split("-")); return f"{MON[m-1]} {dd}, {y}"
    except Exception: return str(dt or "")
def money(v):
    try: v = float(v); return f"${v:,.0f}" if v == int(v) else f"${v:,.2f}"
    except Exception: return str(v or "")
def _ord(n): return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
def date_span(dates):
    """'Nov 21st 2026' or 'Dec 20th - 23rd 2026' or 'Dec 31st 2026 - Jan 2nd 2027'"""
    ds = sorted(datetime.date.fromisoformat(x) for x in dates if x)
    if not ds: return ""
    a, b = ds[0], ds[-1]
    if a == b: return f"{MON[a.month-1]} {_ord(a.day)} {a.year}"
    if a.year != b.year: return f"{MON[a.month-1]} {_ord(a.day)} {a.year} - {MON[b.month-1]} {_ord(b.day)} {b.year}"
    if a.month != b.month: return f"{MON[a.month-1]} {_ord(a.day)} - {MON[b.month-1]} {_ord(b.day)} {a.year}"
    return f"{MON[a.month-1]} {_ord(a.day)} - {_ord(b.day)} {a.year}"
def doc_name(terms):
    """Ibrahim's convention: 'Emanant Visuals – <Client> – <dates>' (+ city, ST if outside Houston)."""
    f = terms["fields"]; who = (f.get("client_names") or f.get("first_names") or "Client").strip()
    span = date_span([x.get("date") for x in terms.get("days", [])])
    city = (f.get("city_state") or "").strip()
    houston = (not city) or city.lower().startswith("houston")
    name = f"Emanant Visuals – {who} – {span}" + ("" if houston else f" – {city}")
    return re.sub(r'[/\\:*?"<>|]', "-", name).strip(" –")
def render(kind, fill, out):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = os.path.join(tempfile.gettempdir(), f".fill_{os.getpid()}_{time.time_ns()}.json")
    json.dump(fill, open(tmp, "w"))
    try:
        if kind == "contract":
            cmd = [VENV_PY, os.path.join(CDIR, "render_contract.py"), "--content", "contract_final_content", "--name", "x", "--clean", "--fill", tmp, "--out", out]
        else:
            cmd = [VENV_PY, os.path.join(CDIR, "render_questionnaire.py"), "--fill", tmp, "--out", out]
        env = dict(os.environ, PYTHONPATH=CONTENT_DIR) if CONTENT_DIR else None
        r = subprocess.run(cmd, cwd=CDIR, capture_output=True, text=True, timeout=120, env=env)
        if r.returncode != 0: raise RuntimeError(r.stderr[-400:])
    finally:
        os.remove(tmp)
    return [out + ".pdf", out + ".docx"]
def build_fill(terms):
    f = dict(terms["fields"]); days = terms.get("days", []); plan = terms.get("plan", [])
    f["issue_date"] = pretty(terms["issue"]); f["sign_by_date"] = pretty(terms["sign_by"])
    f["event_dates"] = " · ".join(f"{pretty(d['date'])}" + (f" ({d['event']})" if d.get("event") else "") for d in days)
    if days:
        f.setdefault("start_time", days[0].get("start", "")); f.setdefault("end_time", days[0].get("end", ""))
        if len(days) > 1 and not f.get("start_time"): f["start_time"] = "See each day below"
    f["total"] = money(terms.get("total")); f["retainer"] = money(terms.get("retainer"))
    f["balance"] = money((terms.get("total") or 0) - (terms.get("retainer") or 0))
    for i, p in enumerate(plan[:3], 1):
        f[f"plan_{i}_label"] = p.get("label", ""); f[f"plan_{i}_amount"] = money(p.get("amount")); f[f"plan_{i}_due"] = pretty(p.get("due"))
    if days and days[0].get("date"):
        q = datetime.date.fromisoformat(days[0]["date"]) - datetime.timedelta(days=28); f["questionnaire_due"] = pretty(q.isoformat())
    f["coverage_rows"] = [[str(i), d.get("event", ""), pretty(d.get("date")), d.get("start", ""), d.get("end", ""), str(d.get("hours", ""))] for i, d in enumerate(days, 1)]
    return f
def activate_signed(d, lead, pdf_bytes=None):
    """Contract signed: payment plan goes live, signed copy filed, questionnaire prepared and emailed to Eman."""
    t = lead.get("contract_terms") or {}
    lead["contract"] = "signed"
    if lead.get("status") in ("open", "unanswered", "ghosted", "lost"): lead["status"] = "booked"
    notes = []
    if t:
        lead["total"] = t.get("total")
        if not lead.get("schedule"):
            sched = [{"label": "Retainer (due at signing)", "due": today(), "amount": t.get("retainer"), "paid": False}] if t.get("retainer") else []
            sched += [{"label": p["label"], "due": p.get("due", ""), "amount": p.get("amount"), "paid": False} for p in t.get("plan", []) if p.get("amount")]
            lead["schedule"] = sched
        if lead.get("retainer") not in ("paid", "partial"): lead["retainer"] = "unpaid"
        lead["balance"] = "due"
        name = doc_name(t); t["signed_on"] = today()
        if pdf_bytes:
            os.makedirs(SIGNED, exist_ok=True); sp = os.path.join(SIGNED, name + ".pdf")
            open(sp, "wb").write(pdf_bytes); t["signed_file"] = sp; notes.append("Signed copy saved to Signed Contracts.")
        try:
            qfiles = render("questionnaire", build_fill(t), os.path.join(QDIR, name + " – Questionnaire"))
            t["questionnaire_files"] = qfiles
            send_mail(FROM_EMAIL, f"[Emanant HQ] Questionnaire ready to send: {name}",
                      f"{lead['client']} signed their contract. 🎉\n\nAttached is their Client To-Do Questionnaire with Section A pre-filled from the signed agreement. Review it and send it to the client whenever you're ready.\n\nReturn-by date: {build_fill(t).get('questionnaire_due','')}\n\n— Emanant HQ", attachments=qfiles)
            notes.append("Questionnaire emailed to Eman.")
        except Exception as ex:
            notes.append(f"Questionnaire not sent: {ex}")
    A = d.setdefault("alerts", []); n = max([int(a["id"][1:]) for a in A] + [0]) + 1
    A.append({"id": f"A{n:04d}", "at": evtime.now_ct().isoformat(timespec="minutes"), "type": "contract_signed", "title": f"Contract signed: {lead['client']}",
              "detail": "Payment plan is now live. " + " ".join(notes), "email_id": f"signed:{lead['id']}:{today()}", "from_email": "", "lead_id": lead["id"], "done": False, "unread": False})
    return notes

# ---------------- calendar ----------------
_MONTHS = {m.lower(): i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_TIME = re.compile(r"\b\d{1,2}(?::\d{2})?\s*(?:-|–|to)\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)\b|\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b|after (?:maghrib|isha|asr|dhuhr|zuhr)", re.I)
def _dates_in(text, year_hint):
    out = []
    for m in re.finditer(r"(20\d\d)-(\d\d)-(\d\d)", text): out.append(m.group(0))
    for m in re.finditer(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?!\d)(?:st|nd|rd|th)?((?:\s*(?:,|&|and)\s*\d{1,2}(?!\d)(?:st|nd|rd|th)?)*)(?:,?\s*(20\d\d))?", text, re.I):
        mo = _MONTHS[m.group(1).lower()[:3]]; y = int(m.group(4) or year_hint)
        for dd in [m.group(2)] + re.findall(r"\d{1,2}", m.group(3) or ""):
            if 1 <= int(dd) <= 31: out.append(f"{y}-{mo:02d}-{int(dd):02d}")
    return out
def calendar_events(d):
    ev = []
    for l in d["leads"]:
        if not l.get("event") or l["client"].startswith("TEST"): continue
        t = l.get("contract_terms") or {}
        if t.get("days"):
            days = [(x["date"], x.get("event", ""), " – ".join(v for v in (x.get("start"), x.get("end")) if v and v != "TBD")) for x in t["days"]]
        else:
            y = int(l["event"][:4]); ds = sorted(set([l["event"]] + [x for x in _dates_in(re.sub(r"\((?:was|originally)[^)]*\)", "", l.get("event_text") or "", flags=re.I), y) if abs(int(x[:4]) - y) <= 1]))
            txt = " ".join(str(l.get(k) or "") for k in ("event_text", "venue", "notes", "action_note"))
            tm = [m.group(0) for m in _TIME.finditer(txt) if not re.match(r"0\d:\d\d", m.group(0))]
            days = [(x, "", tm[0] if tm and len(ds) == 1 else "") for x in ds]
        for date, label, time_ in days:
            ev.append({"date": date, "lead_id": l["id"], "client": l["client"], "status": l["status"], "service": (l.get("service") or "").replace("_", " "),
                       "venue": l.get("venue") or "", "label": label, "time": time_})
    return ev

ENUMS = {
    "status": {"booked", "completed", "open", "unanswered", "ghosted", "lost"},
    "replied": {"yes", "no"},
    "contract": {"signed", "sent", "not_sent", "unknown", "n/a"},
    "retainer": {"paid", "partial", "unpaid", "unknown", "n/a"},
    "balance": {"paid_in_full", "partial", "due", "unknown", "n/a"},
    "gallery": {"yes", "no", "unknown", "n/a"},
    "review": {"received", "requested", "none"},
    "lost_reason": {"went_with_other", "price", "client_ghosted", "changed_plans", "date_conflict", "date_passed", "travel", "no_reply_us", "service_gap", "other", ""},
    "fault": {"ours", "client", "timing", "unknown"},
}
TEXT = {"action_note", "notes", "venue", "quote", "client"}
DATES = {"event", "inquiry", "last_contact"}
NUMS = {"total", "paid"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def today():
    return evtime.today_ct().isoformat()

def load():
    if db.CLOUD: return db.load()
    with open(DATA_PATH) as f:
        return json.load(f)

def store(data, change):
    if db.CLOUD: return db.store(data)  # no file backups / changelog in the cloud (Phase 7 backs up)
    os.makedirs(BACKUPS, exist_ok=True)
    stamp = evtime.now_ct().strftime("%Y%m%d-%H%M%S-%f")
    shutil.copy2(DATA_PATH, os.path.join(BACKUPS, f"tracker_data.{stamp}.json"))
    olds = sorted(os.listdir(BACKUPS))
    for f in olds[:-200]:
        os.remove(os.path.join(BACKUPS, f))
    data.setdefault("changelog", []).append(dict(change, at=evtime.now_ct().isoformat(timespec="seconds"), by="dashboard"))
    tmp = DATA_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, DATA_PATH)

def validate(field, value):
    if field in ENUMS:
        if value not in ENUMS[field]: raise ValueError(f"bad value for {field}")
        return value
    if field in DATES:
        if value in ("", None): return ""
        if not DATE_RE.match(str(value)): raise ValueError("date must be YYYY-MM-DD")
        return value
    if field in NUMS:
        if value in ("", None): return None
        return float(value) if float(value) != int(float(value)) else int(float(value))
    if field in TEXT:
        return str(value or "")[:1000]
    raise ValueError(f"field {field} is not editable")

class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        self.path = self.path.split("?")[0]
        if self.path in ("/", "/index.html"):
            html = open(TEMPLATE).read().replace("__BOOT__", "null").replace("__PRIVACY_OPTIONS__", privacy_options_html())
            return self._send(200, html, "text/html")
        if self.path == "/api/data":
            d = load()
            pays = db.payments() if db.CLOUD else (json.load(open(PAY_PATH)) if os.path.exists(PAY_PATH) else [])
            return self._send(200, json.dumps({"today": today(), "leads": d["leads"], "vendors": d["vendors"], "payments": pays, "finance": d.get("finance", {}), "alerts": d.get("alerts", []), "ignore_senders": d.get("ignore_senders", []), "watch_senders": d.get("watch_senders", [])}, ensure_ascii=False))
        if self.path == "/api/brief":
            bp, ap = os.path.join(DATA_DIR, "brief_latest.json"), os.path.join(DATA_DIR, "brief_ack.json")
            if db.CLOUD:
                b = db.read_doc("brief_latest"); ack = (db.read_doc("brief_ack") or {}).get("id")
            else:
                b = json.load(open(bp)) if os.path.exists(bp) else None
                ack = json.load(open(ap)).get("id") if os.path.exists(ap) else None
            return self._send(200, json.dumps({"brief": b, "acked": bool(b) and ack == b.get("id")}, ensure_ascii=False))
        if self.path == "/calendar":
            return self._send(200, open(os.path.join(HERE, "calendar.html")).read(), "text/html")
        if self.path == "/api/calendar":
            return self._send(200, json.dumps(calendar_events(load()), ensure_ascii=False))
        if self.path.startswith("/docs/"):
            import urllib.parse
            name = os.path.basename(urllib.parse.unquote(self.path[6:]))
            M = {"EMANANT VISUALS - CONTRACT - VFinal": "contract", "EMANANT VISUALS - Client To-Do Questionnaire - VFinal": "questionnaire"}
            stem, ext = os.path.splitext(name)
            fp = os.path.join(SERVED_DIR, M.get(stem, "-") + ext)
            if not name or not os.path.isfile(fp): return self._send(404, "not found", "text/plain")
            ctype = "application/pdf" if name.endswith(".pdf") else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            b = open(fp, "rb").read()
            self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b)))
            self.send_header("Content-Disposition", ("inline" if name.endswith(".pdf") else "attachment") + "; filename*=UTF-8''" + urllib.parse.quote(name))
            self.send_header("Cache-Control", "no-store"); self.end_headers(); return self.wfile.write(b)
        self._send(404, '{"error":"not found"}')

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            with db.locked(LOCK):
                d = load()
                if self.path == "/api/update":
                    lead = next((l for l in d["leads"] if l.get("id") == body.get("id")), None)
                    if not lead: return self._send(404, "lead not found", "text/plain")
                    field = body.get("field"); value = validate(field, body.get("value"))
                    old = lead.get(field); lead[field] = value
                    if field == "contract" and value == "signed" and old != "signed" and lead.get("contract_terms"): activate_signed(d, lead)
                    if field == "event": lead["event_text"] = value
                    store(d, {"id": lead["id"], "client": lead["client"], "field": field, "old": old, "new": value})
                    return self._send(200, json.dumps({"lead": lead}, ensure_ascii=False))
                if self.path == "/api/alert":
                    al = next((a for a in d.get("alerts", []) if a["id"] == body.get("id")), None)
                    if not al: return self._send(404, "alert not found", "text/plain")
                    act = body.get("action")
                    al["done"] = act != "undo"; al["done_at"] = today() if al["done"] else ""
                    ig = d.setdefault("ignore_senders", [])
                    fe = (al.get("from_email") or "").lower()
                    dom = ".".join(fe.split("@")[-1].split(".")[-2:]) if "@" in fe else ""
                    if act == "ignore":
                        al["ignored"] = True
                        for x in (fe, "@" + dom if dom else ""):
                            if x and x not in ig: ig.append(x)
                    elif act == "undo" and al.get("ignored"):
                        al["ignored"] = False
                        for x in (fe, "@" + dom):
                            if x in ig: ig.remove(x)
                    if body.get("lead_id"): al["lead_id"] = body["lead_id"]
                    store(d, {"id": al["id"], "client": al.get("title", ""), "field": "alert", "old": None, "new": "done" if al["done"] else "reopened"})
                    return self._send(200, json.dumps({"alert": al}, ensure_ascii=False))
                if self.path == "/api/brief-ack":
                    ack = {"id": body.get("id"), "at": evtime.now_ct().isoformat(timespec="minutes")}
                    if db.CLOUD: db.write_doc("brief_ack", ack)
                    else: json.dump(ack, open(os.path.join(DATA_DIR, "brief_ack.json"), "w"))
                    return self._send(200, "{}")
                if self.path == "/api/open-folder":
                    if self.client_address[0] != "127.0.0.1": return self._send(403, "local only", "text/plain")
                    sub = {"contracts": "Contracts", "drafts": "Contract Drafts", "signed": "Signed Contracts", "questionnaires": "Questionnaires"}.get(body.get("folder"))
                    if not sub: return self._send(400, "bad folder", "text/plain")
                    fp = os.path.join(EVDOCS, sub); os.makedirs(fp, exist_ok=True); subprocess.run(["open", fp])
                    return self._send(200, "{}")
                if self.path == "/api/contract/create":
                    lead = next((l for l in d["leads"] if l.get("id") == body.get("id")), None)
                    if not lead: return self._send(404, "lead not found", "text/plain")
                    issue = today(); sign_by = (evtime.today_ct() + datetime.timedelta(days=7)).isoformat()
                    days = [x for x in body.get("days", []) if x.get("date")]
                    plan = [x for x in body.get("plan", []) if x.get("amount") not in (None, "")]
                    for x in plan: x["amount"] = validate("total", x["amount"])
                    terms = {"fields": body.get("fields", {}), "days": days, "plan": plan, "issue": issue, "sign_by": sign_by,
                             "total": validate("total", body.get("total")), "retainer": validate("total", body.get("retainer"))}
                    terms["fields"].setdefault("rep_name", "")
                    name = doc_name(terms); terms["name"] = name
                    files = render("contract", build_fill(terms), os.path.join(DRAFTS, name + " – Contract"))
                    terms["draft_files"] = files
                    lead["contract_terms"] = terms; lead["total"] = terms["total"]; lead["contract"] = "not_sent"
                    if days: lead["event"] = days[0]["date"]
                    store(d, {"id": lead["id"], "client": lead["client"], "field": "contract_terms", "old": None, "new": name})
                    try:
                        send_mail(FROM_EMAIL, f"[Emanant HQ] Contract draft to review: {name}",
                                  f"Contract draft for {lead['client']} is attached (PDF to review, Word to edit).\n\nSign-by date: {pretty(sign_by)} (7 days). Create the contract on the day you send it, so the 7 days count from sending.\n\nNext:\n1. Review and edit if needed.\n2. Upload the PDF to DocuSeal, place the signature/date fields, and send it to the client.\n3. In the dashboard, set Contract → Sent.\nWhen DocuSeal emails you the signed copy, the dashboard marks it Signed and starts the payment plan automatically.\n\n— Emanant HQ", attachments=files)
                        mailed = True
                    except Exception as ex:
                        mailed = str(ex)
                    return self._send(200, json.dumps({"lead": lead, "files": files, "mailed": mailed}, ensure_ascii=False))
                if self.path == "/api/contract-signed":
                    if self.client_address[0] != "127.0.0.1": return self._send(403, "local only", "text/plain")
                    lead = next((l for l in d["leads"] if l.get("id") == body.get("lead_id")), None)
                    if not lead: return self._send(404, "lead not found", "text/plain")
                    import base64
                    pdf = base64.b64decode(body["pdf_b64"]) if body.get("pdf_b64") else None
                    notes = activate_signed(d, lead, pdf)
                    store(d, {"id": lead["id"], "client": lead["client"], "field": "contract", "old": "sent", "new": "signed (DocuSeal)"})
                    return self._send(200, json.dumps({"lead": lead, "notes": notes}, ensure_ascii=False))
                if self.path == "/api/send-reply":
                    al = next((a for a in d.get("alerts", []) if a["id"] == body.get("id")), None)
                    if not al or not al.get("from_email"): return self._send(404, "alert/sender not found", "text/plain")
                    text = str(body.get("body", "")).strip()
                    if len(text) < 20: return self._send(400, "message too short", "text/plain")
                    subj = str(body.get("subject") or ("Re: " + (al.get("detail") or "Your message")))[:200]
                    mid = send_mail(al["from_email"], subj, text, al.get("email_id"))
                    al["clarify_sent"] = today(); al["awaiting_reply"] = True; al["done"] = True; al["done_at"] = today()
                    w = d.setdefault("watch_senders", [])
                    if al["from_email"].lower() not in w: w.append(al["from_email"].lower())
                    store(d, {"id": al["id"], "client": al.get("title", ""), "field": "email_sent", "old": None, "new": subj})
                    return self._send(200, json.dumps({"alert": al}, ensure_ascii=False))
                if self.path == "/api/alert-meta":
                    if self.client_address[0] != "127.0.0.1": return self._send(403, "local only", "text/plain")
                    changed = False
                    for a in d.get("alerts", []):
                        if a.get("email_id") in body:
                            u = bool(body[a["email_id"]])
                            if a.get("unread") != u: a["unread"] = u; changed = True
                    if changed: store(d, {"id": "alerts", "client": "", "field": "unread", "old": None, "new": "sync"})
                    return self._send(200, '{"ok":true}')
                if self.path == "/api/alert-new":
                    if self.client_address[0] != "127.0.0.1": return self._send(403, "local only", "text/plain")
                    A = d.setdefault("alerts", [])
                    eid = body.get("email_id")
                    if eid and any(a.get("email_id") == eid or eid in (a.get("email_ids") or []) for a in A):
                        return self._send(200, json.dumps({"dup": True}))
                    fe = (body.get("from_email") or "").lower()
                    def lead_by_email(addr):
                        if not addr: return []
                        return [l for l in d["leads"] if addr in ((l.get("src_email") or "").lower(), (l.get("alt_email") or "").lower())]
                    # one lead per person per occasion: a repeat form/email from an ACTIVE lead attaches to it instead of creating a new lead
                    if body.get("create_lead"):
                        act = [l for l in lead_by_email(fe) if l.get("status") in ("unanswered", "open", "booked")]
                        if act:
                            body["lead_id"] = act[0]["id"]; body.pop("create_lead")
                            body["type"] = "client_email"; body["title"] = f"Repeat inquiry from {act[0]['client']}"
                    if not body.get("lead_id") and fe:
                        ls = lead_by_email(fe)
                        if len(ls) == 1: body["lead_id"] = ls[0]["id"]
                    # merge into an open alert for the same lead (or same sender) instead of stacking alerts
                    tgt = None
                    if body.get("type") not in ("reminder", "contract_signed", "zelle", "payment"):
                        for a in reversed(A):
                            if a.get("done") or a.get("type") in ("reminder", "contract_signed", "zelle", "payment"): continue
                            if (body.get("lead_id") and a.get("lead_id") == body.get("lead_id")) or (fe and (a.get("from_email") or "").lower() == fe):
                                tgt = a; break
                    if tgt and not body.get("create_lead"):
                        tgt.setdefault("email_ids", []).append(eid)
                        tgt["count"] = tgt.get("count", 1) + 1
                        tgt["detail"] = (f"[{(body.get('at') or '')[:16]}] " + str(body.get("detail", ""))[:300] + "\n" + tgt.get("detail", ""))[:1500]
                        tgt["at"] = max(tgt.get("at") or "", body.get("at") or evtime.now_ct().isoformat(timespec="minutes"))
                        tgt["unread"] = True
                        if body.get("lead_id"): tgt["lead_id"] = body["lead_id"]
                        store(d, {"id": tgt["id"], "client": tgt["title"], "field": "alert", "old": None, "new": "merged"})
                        return self._send(200, json.dumps({"alert": tgt, "merged": True}, ensure_ascii=False))
                    n = max([int(a["id"][1:]) for a in A] + [0]) + 1
                    al = {"id": f"A{n:04d}", "at": body.get("at") or evtime.now_ct().isoformat(timespec="minutes"), "type": body.get("type", "email"),
                          "title": str(body.get("title", ""))[:200], "detail": str(body.get("detail", ""))[:600], "email_id": body.get("email_id"),
                          "from_email": body.get("from_email", ""), "lead_id": body.get("lead_id"), "done": bool(body.get("done")), "unread": bool(body.get("unread", True))}
                    lead = None
                    if body.get("create_lead"):
                        L = body["create_lead"]
                        m = max([int(l["id"][1:]) for l in d["leads"] if str(l.get("id", "")).startswith("L")] + [0]) + 1
                        lead = dict(id=f"L{m:03d}", client=str(L.get("client") or "New inquiry")[:120], channel=L.get("channel", "Website form"), service=L.get("service", "unknown"),
                                    inquiry=today(), event=L.get("event") if DATE_RE.match(str(L.get("event") or "")) else "", event_text=str(L.get("event_text", ""))[:120],
                                    venue="", replied="no", status="unanswered", quote="", total=None, paid=None, contract="n/a", retainer="n/a", balance="n/a",
                                    gallery="n/a", review="none", lost_reason="", fault="unknown", price_obj=False, source=L.get("source", ""),
                                    notes=str(L.get("notes", ""))[:1000], src_email=L.get("src_email", ""), ig_ref="", action_note="")
                        d["leads"].append(lead); al["lead_id"] = lead["id"]
                        # fold any earlier open alerts from this sender into the new lead's alert
                        for o in [x for x in A if not x.get("done") and fe and (x.get("from_email") or "").lower() == fe]:
                            al.setdefault("email_ids", []).extend([o.get("email_id")] + (o.get("email_ids") or []))
                            al["detail"] = (al["detail"] + f"\n[earlier {o.get('at','')[:16]}] " + (o.get("detail") or ""))[:1500]
                            al["count"] = al.get("count", 1) + o.get("count", 1); A.remove(o)
                    A.append(al)
                    store(d, {"id": al["id"], "client": al["title"], "field": "alert", "old": None, "new": al["type"]})
                    return self._send(200, json.dumps({"alert": al, "lead": lead}, ensure_ascii=False))
                if self.path == "/api/finance":
                    if body.get("field") != "collected_2026_manual": return self._send(400, "not editable", "text/plain")
                    fin = d.setdefault("finance", {}); old = fin.get("collected_2026_manual")
                    fin["collected_2026_manual"] = validate("total", body.get("value")); fin["as_of"] = today(); fin["source"] = "edited in dashboard"
                    store(d, {"id": "finance", "client": "", "field": "collected_2026_manual", "old": old, "new": fin["collected_2026_manual"]})
                    return self._send(200, json.dumps({"finance": fin}))
                if self.path == "/api/schedule":
                    lead = next((l for l in d["leads"] if l.get("id") == body.get("id")), None)
                    if not lead: return self._send(404, "lead not found", "text/plain")
                    if body.get("action") == "add":
                        amt = validate("total", body.get("amount"))
                        if amt is None: return self._send(400, "amount required", "text/plain")
                        inst = {"label": str(body.get("label") or "Payment")[:120], "due": validate("event", body.get("due")), "amount": amt, "paid": bool(body.get("paid"))}
                        if inst["paid"]:
                            inst["paid_on"] = today(); lead["paid"] = (lead.get("paid") or 0) + amt
                        lead.setdefault("schedule", []).append(inst)
                        lead["schedule"].sort(key=lambda x: x.get("due") or "")
                        if lead.get("balance") in (None, "n/a", "unknown"): lead["balance"] = "due"
                        store(d, {"id": lead["id"], "client": lead["client"], "field": "schedule", "old": None, "new": inst})
                        return self._send(200, json.dumps({"lead": lead}, ensure_ascii=False))
                    S = lead.get("schedule") or []
                    i = int(body.get("index", -1))
                    if not 0 <= i < len(S): return self._send(400, "bad installment", "text/plain")
                    inst = S[i]; old = dict(inst)
                    if body.get("action") == "delete":
                        if inst.get("paid"): lead["paid"] = max(0, (lead.get("paid") or 0) - (inst.get("amount") or 0))
                        S.pop(i)
                    elif body.get("action") == "update":
                        amt = validate("total", body.get("amount", inst.get("amount")))
                        was_paid, now_paid = bool(inst.get("paid")), bool(body.get("paid", inst.get("paid")))
                        delta = (amt or 0) * now_paid - (inst.get("amount") or 0) * was_paid
                        inst.update(label=str(body.get("label", inst.get("label")) or "Payment")[:120], due=validate("event", body.get("due", inst.get("due"))), amount=amt, paid=now_paid)
                        inst["paid_on"] = (inst.get("paid_on") or today()) if now_paid else ""
                        lead["paid"] = max(0, (lead.get("paid") or 0) + delta)
                        S.sort(key=lambda x: x.get("due") or "")
                    else:
                        return self._send(400, "unknown action", "text/plain")
                    if S and all(x.get("paid") for x in S): lead["balance"] = "paid_in_full"
                    elif S and any(x.get("paid") for x in S): lead["balance"] = "partial"
                    elif S: lead["balance"] = "due"
                    store(d, {"id": lead["id"], "client": lead["client"], "field": f"schedule[{i}]", "old": old, "new": body.get("action")})
                    return self._send(200, json.dumps({"lead": lead}, ensure_ascii=False))
                if self.path == "/api/pay":
                    lead = next((l for l in d["leads"] if l.get("id") == body.get("id")), None)
                    if not lead or not lead.get("schedule"): return self._send(404, "no schedule", "text/plain")
                    i = int(body.get("index", -1))
                    if not 0 <= i < len(lead["schedule"]): return self._send(400, "bad installment", "text/plain")
                    inst = lead["schedule"][i]
                    if not inst.get("paid"):
                        inst["paid"] = True; inst["paid_on"] = today()
                        lead["paid"] = (lead.get("paid") or 0) + (inst.get("amount") or 0)
                        if all(x.get("paid") for x in lead["schedule"]): lead["balance"] = "paid_in_full"
                    store(d, {"id": lead["id"], "client": lead["client"], "field": f"schedule[{i}].paid", "old": False, "new": True})
                    return self._send(200, json.dumps({"lead": lead}, ensure_ascii=False))
                if self.path == "/api/add":
                    client = str(body.get("client", "")).strip()
                    if not client: return self._send(400, "client name required", "text/plain")
                    n = max([int(l["id"][1:]) for l in d["leads"] if str(l.get("id", "")).startswith("L")] + [0]) + 1
                    lead = dict(id=f"L{n:03d}", client=client, channel=body.get("channel", ""), service=body.get("service", "unknown"),
                                inquiry=validate("inquiry", body.get("inquiry") or today()), event=validate("event", body.get("event")),
                                event_text=body.get("event") or "", venue="", replied=validate("replied", body.get("replied", "no")),
                                status=validate("status", body.get("status", "unanswered")), quote="", total=None, paid=None,
                                contract="n/a", retainer="n/a", balance="n/a", gallery="n/a", review="none", lost_reason="", price_obj=False,
                                source="", notes=str(body.get("notes", ""))[:1000], src_email="", ig_ref="", action_note="")
                    d["leads"].append(lead)
                    store(d, {"id": lead["id"], "client": client, "field": "*", "old": None, "new": "added"})
                    return self._send(200, json.dumps({"lead": lead}, ensure_ascii=False))
            self._send(404, "not found", "text/plain")
        except ValueError as e:
            self._send(400, str(e), "text/plain")
        except Exception as e:
            self._send(500, f"error: {e}", "text/plain")

    def log_message(self, *a):
        pass

if __name__ == "__main__":
    print(f"Emanant dashboard on http://{HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
