"""Inbox watcher: turns new emails in Eman's iCloud into dashboard alerts.

Runs every 5 minutes (launchd com.emanantvisuals.watch). Read-only on the mailbox.
- Website form (Formspree)  -> new lead (Unanswered) + alert
- Chase Zelle "You received money" -> payment import + alert
- Email from a known client      -> alert ("client replied")
- Email that looks like an inquiry from someone new -> alert ("possible inquiry")
Alerts stay on the dashboard until someone marks them handled.
"""
import json, os, re, subprocess, sys, email, html, datetime, fcntl, urllib.request
from email import policy
from email.utils import getaddresses, parsedate_to_datetime
import evenv
import evtime
import db

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.environ.get("EV_API", "http://127.0.0.1:8787")         # the dashboard server on this Mac
SHADOW = os.environ.get("EV_SHADOW") == "1"                     # test run: no pop-ups, no Zelle import
MAX_TRIES = 3                                                   # then a person is asked to look
LOCK_PATH = os.path.expanduser(os.environ.get("EV_WATCH_LOCK", "~/Library/Caches/emanant-hq/watch.lock"))
INQ = re.compile(r"\b(wedding|nikkah|nikah|walima|valima|mehndi|mehendi|shaadi|baraat|engagement|photograph\w*|photo ?shoot|session|quote|pricing|price|package|availab\w*|book(ing)?|inquir\w*|event|reception|graduation|maternity)\b", re.I)
NOISE = re.compile(r"(no-?reply|noreply|newsletter|notification|mailer|marketing|news@|info@.*(shop|store)|tiktok|instagram|facebook|apple\.com|amazon|uber|doordash|linkedin|google\.com|pic-time\.com|godaddy\.com)", re.I)
OWN = evenv.need("EV_ICLOUD_LOGIN")
OWN_ADDRESSES = {OWN, *evenv.as_list("EV_BUSINESS_ADDRESSES")}  # mail from these is ours, never a lead
STRICT = re.compile(r"\b(wedding|nikkah|nikah|walima|valima|mehndi|mehendi|shaadi|baraat|photographer|photography|photo ?shoot|engagement (shoot|session|photos)|your (rates|pricing|packages)|quote)\b", re.I)

def hj(*args):
    r = subprocess.run(["himalaya", "--json", *args], capture_output=True, text=True, timeout=240)
    if r.returncode != 0: raise RuntimeError(r.stderr[-300:])
    return json.loads(r.stdout)

def raw(mid, mb="Inbox"):
    return subprocess.run(["himalaya", "message", "read", "--raw", "-m", mb, mid], capture_output=True, timeout=120).stdout

def text_of(m):
    try:
        part = m.get_body(preferencelist=("plain", "html")); t = part.get_content() if part else ""
        if part and part.get_content_type() == "text/html":
            t = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S | re.I)))
    except Exception:
        t = ""
    return re.sub(r"\s+", " ", t)

def history(addr):
    """How many emails this address has exchanged with Eman (inbox + sent). >1 = a known contact, not a stranger."""
    n = 0
    for mb, q in (("Inbox", f"from {addr}"), ("Sent Messages", f"to {addr}")):
        try: n += len(hj("envelope", "search", "-m", mb, "-s", "5", q)["envelopes"])
        except Exception: pass
    return n

def post(path, body):
    if os.environ.get("EV_TEST_FAIL_POSTS") == "1":             # scripts/test_step2.py: simulate the server being down
        raise RuntimeError("test: server unavailable")
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=20))

def notify(title, msg):
    if SHADOW: return
    t = title.replace('"', "'")[:80]; m = msg.replace('"', "'")[:180]
    subprocess.run(["osascript", "-e", f'display notification "{m}" with title "Emanant HQ" subtitle "{t}" sound name "Glass"'], capture_output=True)

def ct_time(d):
    """An email's date (UTC 'YYYY-MM-DDTHH:MM:SSZ' or with an offset) -> Houston time 'YYYY-MM-DD HH:MM'."""
    try:
        t = datetime.datetime.fromisoformat((d or "").replace("Z", "+00:00"))
        if t.tzinfo is None:
            return (d or "")[:16].replace("T", " ")
        return evtime.now_ct(t.astimezone(datetime.timezone.utc)).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return (d or "")[:16].replace("T", " ")


def field(t, name):
    m = re.search(rf"\b{name}:\s*(.+?)(?=\s+\w+:\s|\s+Submitted\b|$)", t, re.I)
    return m.group(1).strip() if m else ""

class State:
    """Which emails were handled. JSON mode: watch_state.json (seen + retry counts). Supabase: the
    emails table (status + attempts) and app_state 'watch_state' (since / last_run / last_ok).
    An email counts as seen only once it was handled (processed or skipped), or after MAX_TRIES
    failures that a person was alerted about."""

    def __init__(self):
        self.meta = db.doc_read("watch_state") or {}
        if db.CLOUD:
            self.rows = db.email_rows()
        else:
            self.rows = {k: ("processed", 0) for k in self.meta.get("seen", [])}
            self.rows.update({k: ("failed", n) for k, n in (self.meta.get("retry") or {}).items()})
        self.changed = {}

    def seen(self, key):
        r = self.rows.get(key)
        return bool(r) and (r[0] in ("processed", "skipped") or (r[0] == "failed" and r[1] >= MAX_TRIES))

    def attempts(self, key):
        return (self.rows.get(key) or ("", 0))[1]

    def mark(self, key, status, folder, attempts=None):
        a = self.attempts(key) if attempts is None else attempts
        self.rows[key] = (status, a)
        self.changed[key] = (key, folder, status, a)

    def save(self, all_ok):
        y = (evtime.today_ct() - datetime.timedelta(days=1)).isoformat()
        prev_ok = self.meta.get("last_ok")
        meta = {"since": min(y, prev_ok) if prev_ok else (y if all_ok else self.meta.get("since") or y),
                "last_run": evtime.now_ct().isoformat(timespec="seconds"),
                "last_ok": y if all_ok else prev_ok}
        if db.CLOUD:
            db.emails_upsert(list(self.changed.values()))
            db.doc_write("watch_state", meta)
        else:
            done = sorted(k for k, r in self.rows.items() if self.seen(k))[-3000:]
            retry = {k: r[1] for k, r in self.rows.items() if r[0] == "failed" and r[1] < MAX_TRIES}
            out = {"since": meta["since"], "seen": done, "last_run": meta["last_run"], "last_ok": meta["last_ok"]}
            if retry: out["retry"] = retry
            db.doc_write("watch_state", out)


def main():
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    lock = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)        # one run at a time
    except BlockingIOError:
        print("another run is still going; skipped"); return
    S = State()
    st = S.meta
    all_ok = True
    # always look back 3 days (IMAP "after" is strict and mail can arrive late around midnight); `seen` dedupes
    since = min(st.get("since") or "9999", (evtime.today_ct() - datetime.timedelta(days=3)).isoformat())
    envs = hj("envelope", "search", "-s", "300", f"after {since} order by date asc")["envelopes"]
    try:  # also screen Junk so inquiries caught by the spam filter aren't missed
        for j in hj("envelope", "search", "-m", "Junk", "-s", "100", f"after {since} order by date asc")["envelopes"]:
            j["junk"] = True; envs.append(j)
    except Exception as ex:
        print("junk scan skipped:", ex)
    data = json.load(urllib.request.urlopen(API + "/api/data", timeout=20))
    known = {l["src_email"].lower(): l for l in data["leads"] if l.get("src_email")}
    ignore = [x.lower() for x in data.get("ignore_senders", [])]
    watching = set(x.lower() for x in data.get("watch_senders", []))
    blocked = lambda f: any(f == x or (x.startswith("@") and (f.endswith(x) or f.endswith("." + x[1:]))) for x in ignore)
    def handle(e, key):
        """Returns 'alert' (an alert was posted) or 'skipped'. Raises on failure (retried next run)."""
        frm = (e["from"][0]["email"] if e.get("from") else "").lower()
        name = (e["from"][0].get("name") if e.get("from") else "") or frm
        subj = e.get("subject") or ""
        when = ct_time(e.get("date", ""))
        if frm in OWN_ADDRESSES: return "skipped"
        if "docuseal" in frm and re.search(r"complet|signed", subj, re.I):
            m = email.message_from_bytes(raw(e["id"], "Junk" if e.get("junk") else "Inbox"), policy=policy.default); t = text_of(m)
            hay = (subj + " " + t).lower()
            cands = [l for l in data["leads"] if l.get("contract_terms") and l.get("contract") != "signed"]
            def score(l):
                sc = 0
                if l.get("src_email") and l["src_email"].lower() in hay: sc += 5
                toks = set(re.findall(r"[a-z]{3,}", (l["client"] + " " + l["contract_terms"]["fields"].get("client_names", "")).lower())) - {"and", "the", "via"}
                sc += sum(1 for x in toks if x in hay)
                return sc
            ranked = sorted(((score(l), l) for l in cands), key=lambda x: -x[0])
            pdf = next((p.get_content() for p in m.iter_attachments() if (p.get_filename() or "").lower().endswith(".pdf")), None)
            if ranked and ranked[0][0] >= 2 and (len(ranked) == 1 or ranked[0][0] > ranked[1][0]):
                import base64
                lead = ranked[0][1]
                post("/api/contract-signed", {"lead_id": lead["id"], "pdf_b64": base64.b64encode(pdf).decode() if pdf else None})
                notify("Contract signed 🎉", lead["client"] + (" · signed PDF saved" if pdf else " · download the signed PDF from DocuSeal"))
            else:
                post("/api/alert-new", {"type": "contract_signed", "title": "DocuSeal: signed contract (match needed)", "detail": subj + " — couldn't tell which client; set their Contract to Signed in the dashboard.", "email_id": key, "at": when})
                notify("Signed contract received", subj)
        elif "formspree" in frm and not subj.lower().startswith("new submission"):
            return "skipped"  # Formspree account mail (verification etc.), not an inquiry
        elif "formspree" in frm:
            m = email.message_from_bytes(raw(e["id"], "Junk" if e.get("junk") else "Inbox"), policy=policy.default); t = text_of(m)
            rt = getaddresses([m.get("Reply-To", "")]); cem = (rt[0][1] if rt else field(t, "email")).lower()
            cname = field(t, "name") or cem; svc = field(t, "service"); msg = field(t, "message")
            body = {"type": "new_inquiry", "title": f"New website inquiry: {cname}", "detail": f"{svc} — {msg}"[:600], "email_id": key, "from_email": cem, "at": when,
                    "create_lead": {"client": cname, "channel": "Website form", "src_email": cem, "notes": f"{svc}: {msg}"[:900], "event_text": ""}}
            post("/api/alert-new", body); notify("New website inquiry", f"{cname}: {svc}")
        elif "chase.com" in frm and "received money" in subj.lower():
            if not SHADOW:
                z = subprocess.run([sys.executable, os.path.join(HERE, "zelle_import.py")], capture_output=True, timeout=600)
                if z.returncode != 0: raise RuntimeError("zelle import failed: " + z.stderr.decode()[-200:])
            m = email.message_from_bytes(raw(e["id"], "Junk" if e.get("junk") else "Inbox"), policy=policy.default); t = text_of(m)
            amt = re.search(r"\$\s?([\d,]+\.\d{2})", t); who = re.search(r"([A-Z][\w'.-]+(?: [A-Z][\w'.-]+){0,3}) sent you money", t)
            a = amt.group(1) if amt else "?"; w = who.group(1) if who else "someone"
            post("/api/alert-new", {"type": "payment", "title": f"Zelle received: ${a} from {w}", "detail": "Check it's matched to the right booking (Financials → Payments received).", "email_id": key, "at": when})
            notify("Payment received", f"${a} from {w}")
        elif frm in watching and frm not in known:
            m = email.message_from_bytes(raw(e["id"], "Junk" if e.get("junk") else "Inbox"), policy=policy.default); t = text_of(m)
            fresh = re.split(r"\sOn .{5,80} wrote:", t)[0][:2000]
            if STRICT.search(subj + " " + fresh) or INQ.search(fresh):
                post("/api/alert-new", {"type": "possible_inquiry", "title": f"Replied with details: {name}", "detail": fresh[:500], "email_id": key, "from_email": frm, "at": when})
                notify("Inquiry details received", f"{name}: {fresh[:80]}")
            else:
                post("/api/alert-new", {"type": "email", "title": f"Reply not about photography: {name}", "detail": "Auto-ignored. Reopen if this is wrong. " + fresh[:400], "email_id": key, "from_email": frm, "at": when, "done": True})
        elif frm in known:
            l = known[frm]
            post("/api/alert-new", {"type": "client_email", "title": f"Email from {l['client']}", "detail": subj, "email_id": key, "from_email": frm, "lead_id": l["id"], "at": when})
            notify("Client emailed", f"{l['client']}: {subj}")
        elif not NOISE.search(frm) and not blocked(frm):
            m = email.message_from_bytes(raw(e["id"], "Junk" if e.get("junk") else "Inbox"), policy=policy.default)
            t = text_of(m)
            # ads/newsletters: mailing-list headers or an unsubscribe link -> not a person writing to us
            if m.get("List-Unsubscribe") or m.get("List-Id") or (m.get("Precedence", "").lower() in ("bulk", "list")) or re.search(r"unsubscribe|opt[- ]out|view (this email )?in (your )?browser", t, re.I):
                return "skipped"
            hit = INQ.search(subj) or STRICT.search(t[:1500])
            if not hit:
                # vague message ("are you free March 3?") from someone who has never emailed before -> ask what it's about
                vague = re.search(r"\b(free|available|availability|book|booking|rates?|prices?|cost|how much|quote|interested|hire|services?)\b", subj + " " + t[:800], re.I) or \
                        re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2}\b|\b\d{1,2}/\d{1,2}\b", t[:800], re.I)
                if not vague or len(t) > 2500 or history(frm) > 1: return "skipped"
                post("/api/alert-new", {"type": "unclear", "title": f"Unclear message: {name}" + (" (in Junk!)" if e.get("junk") else ""), "detail": (subj + " — " + t[:400]).strip(" —"), "email_id": key, "from_email": frm, "at": when})
                notify("Unclear message", f"{name}: {subj or t[:60]}")
                return "alert"
            post("/api/alert-new", {"type": "possible_inquiry", "title": f"Possible inquiry: {name}" + (" (in Junk!)" if e.get("junk") else ""), "detail": subj, "email_id": key, "from_email": frm, "at": when})
            notify("Possible inquiry", f"{name}: {subj}")
        else:
            return "skipped"   # newsletter / noise / blocked sender
        return "alert"

    made = 0
    for e in envs:
        mid = e.get("message-id")
        folder = "junk" if e.get("junk") else "inbox"
        key = mid or f"{folder}:{e['id']}"
        if S.seen(key) or (not mid and S.seen(e["id"])): continue     # older runs keyed by bare id
        try:
            out = handle(e, key)
            S.mark(key, "processed" if out == "alert" else "skipped", folder)
            made += out == "alert"
        except Exception as ex:
            all_ok = False
            n = S.attempts(key) + 1
            print("error on", e["id"], ex)
            if n >= MAX_TRIES:
                try:   # give up only once a person has been told
                    post("/api/alert-new", {"type": "unclear", "title": "Couldn't process an email (check the inbox)",
                                            "detail": f"{(e.get('subject') or '')[:200]} — tried {n} times: {str(ex)[:200]}", "email_id": key,
                                            "from_email": (e["from"][0]["email"] if e.get("from") else "").lower(), "at": ct_time(e.get("date", ""))})
                    S.mark(key, "failed", folder, n)
                except Exception as ex2:
                    print("could not alert about", e["id"], ex2); S.mark(key, "failed", folder, n - 1)
            else:
                S.mark(key, "failed", folder, n)
    # look back from the LAST SUCCESSFUL run (minus a day), so a sleeping/offline laptop never skips emails
    # sign-by reminders (7 days, 3 days, deadline) for contracts sent but not signed
    for l in data["leads"]:
        t = l.get("contract_terms") or {}
        if l.get("contract") != "sent" or not t.get("sign_by"): continue
        left = (datetime.date.fromisoformat(t["sign_by"]) - evtime.today_ct()).days
        for mark, msg in ((3, "3 days left to sign — send a friendly reminder"), (1, "1 day left to sign — last reminder"),
                          (0, "Sign-by deadline today — final notice: unsigned contracts become invalid; the date is not held"), (-1, "Sign-by date passed — offer expired; release the date or re-issue")):
            if (left == mark) or (mark == -1 and left < 0):
                try: post("/api/alert-new", {"type": "reminder", "title": f"{l['client']}: {msg}", "detail": f"Sign-by date {t['sign_by']}. Contract sent but not signed.", "email_id": f"signby:{l['id']}:{mark}", "lead_id": l["id"]})
                except Exception as ex: all_ok = False; print("reminder failed:", ex)
    # Eman's Sent folder: replying to a lead moves it from unanswered -> open (waiting on client) and records last contact
    try:
        sent = hj("envelope", "search", "-m", "Sent Messages", "-s", "200", f"after {since} order by date asc")["envelopes"]
        byaddr = {}
        for l in data["leads"]:
            for a2 in (l.get("src_email"), l.get("alt_email")):
                if a2: byaddr.setdefault(a2.lower(), []).append(l)
        for e in sent:
            k = "sent:" + (e.get("message-id") or e["id"])
            if S.seen(k): continue
            day = ct_time(e["date"])[:10]
            try:
                for t in e.get("to", []) or []:
                    for l in byaddr.get((t.get("email") or "").lower(), []):
                        if l.get("status") in ("completed", "lost") and (l.get("inquiry") or "") < "2026-10-01": continue
                        if l.get("status") == "unanswered": post("/api/update", {"id": l["id"], "field": "status", "value": "open"}); l["status"] = "open"
                        if (l.get("last_contact") or "") < day: post("/api/update", {"id": l["id"], "field": "last_contact", "value": day}); l["last_contact"] = day
                S.mark(k, "processed", "sent")
            except Exception as ex:
                all_ok = False; S.mark(k, "failed", "sent", S.attempts(k) + 1); print("sent update failed:", ex)
    except Exception as ex:
        all_ok = False
        print("sent check skipped:", ex)
    try:
        flags = {(e.get("message-id") or e["id"]): not any(f.get("iana") == "seen" for f in e.get("flags", [])) for e in envs}
        post("/api/alert-meta", flags)
    except Exception as ex:
        print("unread sync skipped:", ex)
    S.save(all_ok)
    print(f"{datetime.datetime.now():%Y-%m-%d %H:%M} checked {len(envs)} emails, {made} alerts" + ("" if all_ok else " (some failed: will retry)"))

if __name__ == "__main__":
    main()
