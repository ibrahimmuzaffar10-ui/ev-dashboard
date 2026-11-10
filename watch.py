"""Inbox watcher: turns new emails in Eman's iCloud into dashboard alerts.

Runs every 5 minutes (launchd com.emanantvisuals.watch). Read-only on the mailbox.
- Website form (Formspree)  -> new lead (Unanswered) + alert
- Chase Zelle "You received money" -> payment import + alert
- Email from a known client      -> alert ("client replied")
- Email that looks like an inquiry from someone new -> alert ("possible inquiry")
Alerts stay on the dashboard until someone marks them handled.
"""
import json, os, re, subprocess, email, html, datetime, urllib.request
from email import policy
from email.utils import getaddresses, parsedate_to_datetime
import evenv

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.expanduser(os.environ.get("EV_DATA_DIR", HERE))
STATE = os.path.join(DATA_DIR, "watch_state.json")
API = "http://127.0.0.1:8787"
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
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=20))

def notify(title, msg):
    t = title.replace('"', "'")[:80]; m = msg.replace('"', "'")[:180]
    subprocess.run(["osascript", "-e", f'display notification "{m}" with title "Emanant HQ" subtitle "{t}" sound name "Glass"'], capture_output=True)

def field(t, name):
    m = re.search(rf"\b{name}:\s*(.+?)(?=\s+\w+:\s|\s+Submitted\b|$)", t, re.I)
    return m.group(1).strip() if m else ""

def main():
    st = json.load(open(STATE)) if os.path.exists(STATE) else {}
    first = not st
    # always look back 3 days (IMAP "after" is strict and mail can arrive late around midnight); `seen` dedupes
    since = min(st.get("since") or "9999", (datetime.date.today() - datetime.timedelta(days=3)).isoformat())
    seen = set(st.get("seen", []))
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
    made = 0
    for e in envs:
        key = e.get("message-id") or e["id"]
        if key in seen: continue
        seen.add(key)
        frm = (e["from"][0]["email"] if e.get("from") else "").lower()
        name = (e["from"][0].get("name") if e.get("from") else "") or frm
        subj = e.get("subject") or ""
        when = e.get("date", "")[:16].replace("T", " ")
        if frm in OWN_ADDRESSES: continue
        try:
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
                made += 1
            elif "formspree" in frm and not subj.lower().startswith("new submission"):
                continue  # Formspree account mail (verification etc.), not an inquiry
            elif "formspree" in frm:
                m = email.message_from_bytes(raw(e["id"], "Junk" if e.get("junk") else "Inbox"), policy=policy.default); t = text_of(m)
                rt = getaddresses([m.get("Reply-To", "")]); cem = (rt[0][1] if rt else field(t, "email")).lower()
                cname = field(t, "name") or cem; svc = field(t, "service"); msg = field(t, "message")
                body = {"type": "new_inquiry", "title": f"New website inquiry: {cname}", "detail": f"{svc} — {msg}"[:600], "email_id": key, "from_email": cem, "at": when,
                        "create_lead": {"client": cname, "channel": "Website form", "src_email": cem, "notes": f"{svc}: {msg}"[:900], "event_text": ""}}
                post("/api/alert-new", body); notify("New website inquiry", f"{cname}: {svc}"); made += 1
            elif "chase.com" in frm and "received money" in subj.lower():
                subprocess.run(["python3", os.path.join(HERE, "zelle_import.py")], capture_output=True, timeout=600)
                m = email.message_from_bytes(raw(e["id"], "Junk" if e.get("junk") else "Inbox"), policy=policy.default); t = text_of(m)
                amt = re.search(r"\$\s?([\d,]+\.\d{2})", t); who = re.search(r"([A-Z][\w'.-]+(?: [A-Z][\w'.-]+){0,3}) sent you money", t)
                a = amt.group(1) if amt else "?"; w = who.group(1) if who else "someone"
                post("/api/alert-new", {"type": "payment", "title": f"Zelle received: ${a} from {w}", "detail": "Check it's matched to the right booking (Financials → Payments received).", "email_id": key, "at": when})
                notify("Payment received", f"${a} from {w}"); made += 1
            elif frm in watching and frm not in known:
                m = email.message_from_bytes(raw(e["id"], "Junk" if e.get("junk") else "Inbox"), policy=policy.default); t = text_of(m)
                fresh = re.split(r"\sOn .{5,80} wrote:", t)[0][:2000]
                if STRICT.search(subj + " " + fresh) or INQ.search(fresh):
                    post("/api/alert-new", {"type": "possible_inquiry", "title": f"Replied with details: {name}", "detail": fresh[:500], "email_id": key, "from_email": frm, "at": when})
                    notify("Inquiry details received", f"{name}: {fresh[:80]}")
                else:
                    post("/api/alert-new", {"type": "email", "title": f"Reply not about photography: {name}", "detail": "Auto-ignored. Reopen if this is wrong. " + fresh[:400], "email_id": key, "from_email": frm, "at": when, "done": True})
                made += 1
            elif frm in known:
                l = known[frm]
                post("/api/alert-new", {"type": "client_email", "title": f"Email from {l['client']}", "detail": subj, "email_id": key, "from_email": frm, "lead_id": l["id"], "at": when})
                notify("Client emailed", f"{l['client']}: {subj}"); made += 1
            elif not NOISE.search(frm) and not blocked(frm):
                m = email.message_from_bytes(raw(e["id"], "Junk" if e.get("junk") else "Inbox"), policy=policy.default)
                t = text_of(m)
                # ads/newsletters: mailing-list headers or an unsubscribe link -> not a person writing to us
                if m.get("List-Unsubscribe") or m.get("List-Id") or (m.get("Precedence", "").lower() in ("bulk", "list")) or re.search(r"unsubscribe|opt[- ]out|view (this email )?in (your )?browser", t, re.I):
                    continue
                hit = INQ.search(subj) or STRICT.search(t[:1500])
                if not hit:
                    # vague message ("are you free March 3?") from someone who has never emailed before -> ask what it's about
                    vague = re.search(r"\b(free|available|availability|book|booking|rates?|prices?|cost|how much|quote|interested|hire|services?)\b", subj + " " + t[:800], re.I) or \
                            re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2}\b|\b\d{1,2}/\d{1,2}\b", t[:800], re.I)
                    if not vague or len(t) > 2500 or history(frm) > 1: continue
                    post("/api/alert-new", {"type": "unclear", "title": f"Unclear message: {name}" + (" (in Junk!)" if e.get("junk") else ""), "detail": (subj + " — " + t[:400]).strip(" —"), "email_id": key, "from_email": frm, "at": when})
                    notify("Unclear message", f"{name}: {subj or t[:60]}"); made += 1
                    continue
                post("/api/alert-new", {"type": "possible_inquiry", "title": f"Possible inquiry: {name}" + (" (in Junk!)" if e.get("junk") else ""), "detail": subj, "email_id": key, "from_email": frm, "at": when})
                notify("Possible inquiry", f"{name}: {subj}"); made += 1
        except Exception as ex:
            print("error on", e["id"], ex)
    # look back from the LAST SUCCESSFUL run (minus a day), so a sleeping/offline laptop never skips emails
    # sign-by reminders (7 days, 3 days, deadline) for contracts sent but not signed
    for l in data["leads"]:
        t = l.get("contract_terms") or {}
        if l.get("contract") != "sent" or not t.get("sign_by"): continue
        left = (datetime.date.fromisoformat(t["sign_by"]) - datetime.date.today()).days
        for mark, msg in ((3, "3 days left to sign — send a friendly reminder"), (1, "1 day left to sign — last reminder"),
                          (0, "Sign-by deadline today — final notice: unsigned contracts become invalid; the date is not held"), (-1, "Sign-by date passed — offer expired; release the date or re-issue")):
            if (left == mark) or (mark == -1 and left < 0):
                try: post("/api/alert-new", {"type": "reminder", "title": f"{l['client']}: {msg}", "detail": f"Sign-by date {t['sign_by']}. Contract sent but not signed.", "email_id": f"signby:{l['id']}:{mark}", "lead_id": l["id"]})
                except Exception: pass
    # Eman's Sent folder: replying to a lead moves it from unanswered -> open (waiting on client) and records last contact
    try:
        sent = hj("envelope", "search", "-m", "Sent Messages", "-s", "200", f"after {since} order by date asc")["envelopes"]
        byaddr = {}
        for l in data["leads"]:
            for a2 in (l.get("src_email"), l.get("alt_email")):
                if a2: byaddr.setdefault(a2.lower(), []).append(l)
        for e in sent:
            k = "sent:" + (e.get("message-id") or e["id"])
            if k in seen: continue
            seen.add(k); day = e["date"][:10]
            for t in e.get("to", []) or []:
                for l in byaddr.get((t.get("email") or "").lower(), []):
                    if l.get("status") in ("completed", "lost") and (l.get("inquiry") or "") < "2026-10-01": continue
                    if l.get("status") == "unanswered": post("/api/update", {"id": l["id"], "field": "status", "value": "open"})
                    if (l.get("last_contact") or "") < day: post("/api/update", {"id": l["id"], "field": "last_contact", "value": day})
    except Exception as ex:
        print("sent check skipped:", ex)
    try:
        flags = {(e.get("message-id") or e["id"]): not any(f.get("iana") == "seen" for f in e.get("flags", [])) for e in envs}
        post("/api/alert-meta", flags)
    except Exception as ex:
        print("unread sync skipped:", ex)
    st = {"since": (datetime.date.today() - datetime.timedelta(days=1)).isoformat() if not st.get("last_ok") else min((datetime.date.today() - datetime.timedelta(days=1)).isoformat(), st["last_ok"]), "seen": sorted(seen)[-3000:], "last_run": datetime.datetime.now().isoformat(timespec="seconds"), "last_ok": (datetime.date.today() - datetime.timedelta(days=1)).isoformat()}
    json.dump(st, open(STATE, "w"))
    print(f"{datetime.datetime.now():%Y-%m-%d %H:%M} checked {len(envs)} emails, {made} alerts")

if __name__ == "__main__":
    main()
