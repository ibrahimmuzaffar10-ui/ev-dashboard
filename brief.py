#!/usr/bin/env python3
"""Emanant HQ twice-daily brief (7 AM / 10 PM Central).
Prints a compact markdown brief of what moved since the last brief + what needs attention,
and saves it to brief_latest.json so the dashboard shows it as a must-read overlay.
Read-only on the tracker; only writes brief_state.json / brief_latest.json."""
import json, os, datetime, re

HERE = os.path.dirname(os.path.abspath(__file__))
import evenv  # noqa: E402  (loads .env.local)
import db  # noqa: E402  (JSON files or Supabase, per EV_BACKEND)
DATA = db.load() if db.CLOUD else json.load(open(os.path.join(db.DATA_DIR, "tracker_data.json")))
PAYS = db.payments_all()
st = db.doc_read("brief_state") or {}
SHADOW = os.environ.get("EV_SHADOW") == "1"   # test runs: no Mac pop-up
import sys
from zoneinfo import ZoneInfo
ct = datetime.datetime.now(ZoneInfo("America/Chicago")).replace(tzinfo=None)
import evtime  # noqa: E402
now = evtime.now_ct()  # Houston time, same clock as alert timestamps
# runs hourly from the scheduler; only speaks at 7 AM and 10 PM Central (robust to the laptop's own time zone)
if "--force" not in sys.argv and not (ct.hour in (7, 22) and ct.minute < 30): sys.exit(0)
since = st.get("last") or (now - datetime.timedelta(hours=15)).isoformat(timespec="seconds")
today = now.date()
L = {l["id"]: l for l in DATA["leads"]}
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
def fd(s):
    try: y, m, d = map(int, str(s)[:10].split("-")); return f"{MON[m-1]} {d}"
    except Exception: return str(s or "")
def money(v):
    try: return f"${float(v):,.0f}"
    except Exception: return str(v)
def name(l): return l["client"]

# ---- what moved since the last brief
moved = []
for a in DATA.get("alerts", []):
    if (a.get("at") or "") <= since[:16]: continue
    if a.get("type") == "reminder": continue
    who = name(L[a["lead_id"]]) if a.get("lead_id") in L else a.get("title", "")
    kind = {"new_inquiry": "🆕 New inquiry", "client_email": "✉️ Client email", "possible_inquiry": "❓ Possible inquiry",
            "payment": "💵 Payment", "contract_signed": "✍️ Contract signed", "unclear": "❓ Unclear message"}.get(a.get("type"), "🔔 " + a.get("type", "alert"))
    cnt = f" ({a['count']} messages)" if a.get("count", 1) > 1 else ""
    moved.append(f"- {kind}: **{who}**{cnt} — {(a.get('detail') or '').splitlines()[0][:110]}")
seen = set(st.get("pays", []))
for p in PAYS:
    if p["email_id"] in seen: continue
    if st.get("pays") is not None:
        who = p.get("client") or (name(L[p["lead_id"]]) if p.get("lead_id") in L else f"{p['sender']} (not matched to a client)")
        moved.append(f"- 💵 Zelle **{money(p['amount'])}** from {who} ({fd(p['date'])})")
for c in DATA.get("changelog", []):
    if (c.get("at") or "") <= since or c.get("by") != "dashboard": continue
    if c.get("field") in ("status", "contract", "retainer", "balance") and c.get("client"):
        moved.append(f"- ✏️ {c['client']}: {c['field']} → {c.get('new')}")

# ---- needs attention
unans = [l for l in DATA["leads"] if l["status"] == "unanswered" and (not l.get("event") or l["event"] >= today.isoformat())]
unans.sort(key=lambda l: l.get("event") or "9999")
soon_shoots, sign_by, due = [], [], []
for l in DATA["leads"]:
    t = l.get("contract_terms") or {}
    days = [x["date"] for x in t.get("days", [])] or ([l["event"]] if l.get("event") else [])
    if l["status"] == "booked":
        for dd in days:
            try: n = (datetime.date.fromisoformat(dd) - today).days
            except Exception: continue
            if 0 <= n <= 3: soon_shoots.append(f"- 📸 **{name(l)}** {fd(dd)}" + (" (today)" if n == 0 else " (tomorrow)" if n == 1 else f" (in {n} days)") + (f" · {l['event_text']}" if l.get("event_text") and l["event_text"][:10] != dd else ""))
    if l.get("contract") == "sent" and t.get("sign_by"):
        n = (datetime.date.fromisoformat(t["sign_by"]) - today).days
        if n <= 2: sign_by.append(f"- ✍️ **{name(l)}** contract " + ("EXPIRED " + fd(t['sign_by']) if n < 0 else f"sign-by {fd(t['sign_by'])}" + (" (today)" if n == 0 else f" ({n} day{'s' if n > 1 else ''} left)")))
    for s in l.get("schedule") or []:
        if s.get("paid") or not s.get("due"): continue
        n = (datetime.date.fromisoformat(s["due"]) - today).days
        if n <= 3: due.append(f"- 💳 **{name(l)}** {money(s['amount'])} {s.get('label','')} " + (f"OVERDUE since {fd(s['due'])}" if n < 0 else f"due {fd(s['due'])}"))
unmatched = [p for p in PAYS if not p.get("lead_id") and p.get("date", "") >= (today - datetime.timedelta(days=14)).isoformat()]

slot = "Morning" if ct.hour < 15 else "Night"

out = [f"## Emanant HQ · {slot} brief · {ct:%a %b %-d, %-I:%M %p} CT"]
out.append(f"**Since last brief:** " + (f"{len(moved)} update(s)" if moved else "no new emails, inquiries or payments"))
out += moved[:15]
if soon_shoots: out += ["", "**Shoots in the next 3 days**"] + soon_shoots
if sign_by: out += ["", "**Contract deadlines**"] + sign_by
if due: out += ["", "**Payments due / overdue**"] + due
if unans:
    out += ["", f"**Waiting on a reply from us ({len(unans)})**"]
    out += [f"- 🟧 {name(l)}" + (f" · {fd(l['event'])}" if l.get("event") else "") + (f" — {l['action_note']}" if l.get("action_note") else "") for l in unans[:10]]
if unmatched:
    out += ["", "**Zelle not matched to a client (last 14 days)**"] + [f"- {money(p['amount'])} from {p['sender']} ({fd(p['date'])})" for p in unmatched]
out += ["", "_Email + website form + Zelle are scanned automatically. Instagram DMs aren't visible yet: tell Hermes about new IG activity._"]
text = "\n".join(out)
print(text)

st["last"] = now.isoformat(timespec="seconds"); st["pays"] = [p["email_id"] for p in PAYS]
db.doc_write("brief_state", st)
db.doc_write("brief_latest", {"id": now.strftime("%Y%m%d%H%M"), "at": now.isoformat(timespec="minutes"), "slot": slot, "text": text}, ensure_ascii=False)

# pop-up on the Mac so the brief gets seen; the full brief opens first thing on the dashboard
try:
    if SHADOW: raise RuntimeError("shadow run: no pop-up")
    import subprocess
    summary = (f"{len(moved)} update(s)" if moved else "No new activity") + f" · {len(unans)} waiting on a reply" + (f" · {len(due)} payment(s) due" if due else "")
    subprocess.run(["osascript", "-e", f'display notification "{summary}. Open the dashboard to read it." with title "Emanant HQ" subtitle "{slot} brief ready" sound name "Glass"'], capture_output=True, timeout=10)
except Exception:
    pass
