#!/usr/bin/env python3
"""Sync into the shared iCloud "Family Calendar" (Ibrahim + Eman):
  - Ibrahim's Gmail calendar events  -> "🟪 <title>"            (copies; Gmail untouched)
  - Emanant bookings (dashboard)     -> "📸 <client> · <what>"   (booked)
  - Emanant open inquiries w/ dates  -> "⏳ HOLD · <client>"      (pending, not confirmed)
Only touches events it created (marked "evsync:" in the notes). Diff-based: adds/removes
only what changed, so Eman's phone isn't spammed. Run: python3 calendar_sync.py [--dry]"""
import json, os, re, subprocess, sys, datetime, urllib.request
import evenv

TARGET = "Family Calendar"
SOURCES = evenv.as_list("EV_CAL_SOURCES")  # calendars copied into the shared calendar
HORIZON = 400  # days ahead
DRY = "--dry" in sys.argv
SEP, RS = "\x1f", "\x1e"

def osa(script, timeout=300):
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0: raise RuntimeError(r.stderr.strip()[:400])
    return r.stdout.rstrip("\n")

def read_cal(name, managed_only=False):
    cond = 'whose start date > ((current date) - 1 * days) and start date < ((current date) + %d * days)' % HORIZON
    s = f'''on base()
set x to current date
set day of x to 1
set year of x to 2026
set month of x to 1
set time of x to 0
return x
end base
set out to ""
set fs to (ASCII character 31)
set rs to (ASCII character 30)
tell application "Calendar"
  set evs to (every event of calendar "{name}" {cond})
  repeat with e in evs
    set d to description of e
    if d is missing value then set d to ""
    {'if d starts with "evsync:" then' if managed_only else 'if true then'}
      set sd to start date of e
      set ed to end date of e
      set out to out & (uid of e) & fs & (summary of e) & fs & ((sd - (my base())) as integer) & fs & ((ed - (my base())) as integer) & fs & (allday event of e) & fs & d & rs
    end if
  end repeat
end tell
return out'''
    rows = []
    for rec in osa(s).split(RS):
        if not rec.strip(): continue
        p = rec.split(SEP)
        if len(p) < 6: continue
        rows.append(dict(uid=p[0], title=p[1], start=int(round(float(p[2]))), end=int(round(float(p[3]))), allday=p[4] == "true", notes=SEP.join(p[5:])))
    return rows

EPOCH = datetime.datetime(2026, 1, 1)
def secs(dt): return int((dt - EPOCH).total_seconds())

# ---------- desired events ----------
want = {}
def add(key, title, start, end, allday, notes=""):
    want[key] = dict(key=key, title=title, start=start, end=end, allday=allday, notes=f"evsync:{key}\n{notes}".strip())

for src in SOURCES:
    for e in read_cal(src):
        if e["notes"].startswith("evsync:"): continue
        add(f"gmail:{e['uid']}", "🟪 " + e["title"], e["start"], e["end"], e["allday"], "Copied from Ibrahim's Gmail calendar (edit it there).")

TR = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\s*(?:-|–|to)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)", re.I)
T1 = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)
def hm(h, m, ap):
    h = int(h) % 12; m = int(m or 0)
    if ap and ap.lower().startswith("p"): h += 12
    return h, m
def times(txt):
    txt = re.sub(r"\d{1,2}:\d{2}\s*(?:AM|PM)\s*-\s*\d{1,2}\s*\w+\s*20\d\d", "", txt or "")  # drop form-submission stamps
    m = TR.search(txt)
    if m:
        ap2 = m.group(6); ap1 = m.group(3) or ap2
        a, b = hm(m.group(1), m.group(2), ap1), hm(m.group(4), m.group(5), ap2)
        if a > b and not m.group(3): a = hm(m.group(1), m.group(2), "am")
        return a, b
    m = T1.search(txt)
    if m:
        a = hm(m.group(1), m.group(2), m.group(3)); return a, (a[0] + 1, a[1])
    return None

data = json.load(urllib.request.urlopen("http://127.0.0.1:8787/api/data"))
cal = json.load(urllib.request.urlopen("http://127.0.0.1:8787/api/calendar"))
L = {l["id"]: l for l in data["leads"]}
now = datetime.date.today()
today = now.isoformat()
for ev in cal:
    l = L.get(ev["lead_id"]); d = ev["date"]
    if not l or d < today or l["status"] not in ("booked", "open", "unanswered") or l["client"].startswith("TEST"): continue
    if l["status"] == "unanswered" and (l.get("inquiry") or "") < (now - datetime.timedelta(days=30)).isoformat(): continue  # stale, never-answered: no hold
    svc = (l.get("service") or "").replace("_", " ").replace("engagement couples", "couples").replace("unknown", "").replace("event other", "event")
    what = ev.get("label") or svc or "shoot"
    booked = l["status"] == "booked"
    title = f"📸 {l['client']} · {what}" if booked else f"⏳ HOLD · {l['client']} · {what} (not confirmed)"
    same_day = sum(1 for x in cal if x["lead_id"] == l["id"]) == 1
    tm = times(ev.get("time") or "") or (times((l.get("event_text") or "") + " " + (l.get("notes") or "")) if same_day and not ev.get("label") else None)
    y, mo, dd = map(int, d.split("-"))
    notes = f"{'BOOKED' if booked else 'PENDING inquiry'} · contract: {l.get('contract')} · retainer: {l.get('retainer')}\n{l.get('venue') or ''}\nEmanant HQ lead {l['id']}"
    if tm:
        (h1, m1), (h2, m2) = tm
        st = datetime.datetime(y, mo, dd, h1, m1); en = datetime.datetime(y, mo, dd, h2, m2)
        if en <= st: en = st + datetime.timedelta(hours=1)
        add(f"ev:{l['id']}:{d}", title, secs(st), secs(en), False, notes)
    else:
        st = datetime.datetime(y, mo, dd)
        add(f"ev:{l['id']}:{d}", title + " · time TBD", secs(st), secs(st + datetime.timedelta(days=1)), True, notes)

# ---------- diff against what we already put in the target ----------
have = read_cal(TARGET, managed_only=True)
def sig(e):
    if e["allday"]: return (e["title"], (EPOCH + datetime.timedelta(seconds=e["start"])).date(), True)
    return (e["title"], e["start"], e["end"], False)
have_by_key = {}
for e in have:
    k = e["notes"].split("\n")[0][len("evsync:"):]
    have_by_key.setdefault(k, []).append(e)
to_del, to_add = [], []
for k, es in have_by_key.items():
    w = want.get(k)
    keep = None
    for e in es:
        if w and keep is None and sig(e) == sig(w): keep = e
        else: to_del.append(e)
for k, w in want.items():
    if not any(sig(e) == sig(w) for e in have_by_key.get(k, [])): to_add.append(w)

def as_str(s): return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
def as_date(n):
    dt = EPOCH + datetime.timedelta(seconds=n)
    return f'(my mk({dt.year}, {dt.month}, {dt.day}, {dt.hour * 3600 + dt.minute * 60}))'
print(f"want {len(want)} · already there {len(have)} · add {len(to_add)} · remove {len(to_del)}")
for w in to_add: print("  +", (EPOCH + datetime.timedelta(seconds=w["start"])).strftime("%a %b %d %H:%M"), w["title"])
for e in to_del: print("  -", e["title"])
if DRY or not (to_add or to_del): sys.exit(0)
lines = ['on mk(y, m, d, t)', 'set x to current date', 'set day of x to 1', 'set year of x to y', 'set month of x to m', 'set day of x to d', 'set time of x to t', 'return x', 'end mk',
         'tell application "Calendar"', f'set c to calendar {as_str(TARGET)}']
for e in to_del:
    lines.append(f'try\ndelete (every event of c whose uid is {as_str(e["uid"])})\nend try')
for w in to_add:
    lines.append(f'make new event at end of events of c with properties {{summary:{as_str(w["title"])}, start date:{as_date(w["start"])}, end date:{as_date(w["end"])}, allday event:{"true" if w["allday"] else "false"}, description:{as_str(w["notes"])}}}')
lines.append('end tell')
osa("\n".join(lines), timeout=600)
print("synced")
