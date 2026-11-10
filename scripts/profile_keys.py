#!/usr/bin/env python3
"""Schema v1 pre-check against the live JSON. Read-only. Prints key NAMES, types and counts
only, never a value, so the output is safe to paste into chat.

Usage (on the Mac):  EV_DATA_DIR=~/EmanantHQ python3 scripts/profile_keys.py
Exit 0 = 0 blockers = the Phase 3 import will not hit a constraint.
"""
import collections, json, os, re, sys

D = os.path.expanduser(os.environ.get("EV_DATA_DIR", "~/EmanantHQ"))
blockers, notes = [], []
# generated columns in the schema: key -> JSON type it must have to fill the column (else NULL)
PROJECTED = {
    "leads": {"id": "str", "client": "str", "status": "str", "event": "str", "src_email": "str", "alt_email": "str", "total": "num", "paid": "num"},
    "alerts": {"id": "str", "type": "str", "at": "str", "lead_id": "str", "email_id": "str", "from_email": "str", "done": "bool"},
    "vendors": {"name": "str"},
    "payments": {"email_id": "str", "date": "str", "amount": "num", "lead_id": "str"},
}
KEY = {"leads": ("id", r"^L[0-9]{3,}$"), "alerts": ("id", r"^A[0-9]{4,}$"), "payments": ("email_id", r".")}


def jtype(v):
    if v is None: return "null"
    if isinstance(v, bool): return "bool"
    if isinstance(v, (int, float)): return "num"
    return {str: "str", list: "list", dict: "dict"}[type(v)]


def has_nul(v):
    return "\\u0000" in json.dumps(v)


def profile(table, items):
    print(f"\n## {table}: {len(items)} items")
    keys = collections.defaultdict(collections.Counter)
    for i, o in enumerate(items):
        if not isinstance(o, dict): blockers.append(f"{table}[{i}] is not an object"); continue
        for k, v in o.items(): keys[k][jtype(v)] += 1
        if has_nul(o): blockers.append(f"{table}[{i}] contains a NUL character")
    for k in sorted(keys, key=lambda k: -sum(keys[k].values())):
        want = PROJECTED[table].get(k)
        odd = sum(n for t, n in keys[k].items() if want and t not in (want, "null"))
        flag = f"  column ({want})" + (f"  note: {odd} of another type -> column NULL" if odd else "") if want else ""
        print(f"  {k:<16} {sum(keys[k].values()):>5}  {dict(keys[k])}{flag}")
        if odd: notes.append(f"{table}.{k}: {odd} value(s) not {want}; kept in raw, column NULL")
    if table in KEY:
        k, rx = KEY[table]
        vals = [o.get(k) for o in items if isinstance(o, dict)]
        bad = sum(1 for v in vals if not isinstance(v, str) or not re.match(rx, v))
        dup = len([v for v in vals if isinstance(v, str)]) - len({v for v in vals if isinstance(v, str)})
        if bad: blockers.append(f"{table}.{k}: {bad} item(s) missing, not text, or wrong format (it is the primary key)")
        if dup: blockers.append(f"{table}.{k}: {dup} duplicate(s) (it is the primary key)")
    if table == "alerts":
        e = [o.get("email_id") for o in items if isinstance(o, dict) and o.get("email_id")]
        if len(e) != len(set(e)): notes.append(f"alerts.email_id: {len(e) - len(set(e))} repeat(s) (allowed, not unique)")


t = json.load(open(os.path.join(D, "tracker_data.json")))
print("# tracker_data.json top-level keys:", list(t))
for k in t:
    if k == "changelog": print(f"  changelog: {len(t[k])} entries -> NOT migrated (decision 11/10)")
    elif k not in ("leads", "alerts", "vendors"): print(f"  {k}: {jtype(t[k])} -> app_state")
for name in ("leads", "alerts", "vendors"): profile(name, t.get(name, []))
pp = os.path.join(D, "payments.json")
if os.path.exists(pp): profile("payments", json.load(open(pp)))
for f in ("watch_state", "brief_latest", "brief_state", "brief_ack"):
    p = os.path.join(D, f + ".json")
    if not os.path.exists(p): print(f"\n{f}.json: not found"); continue
    v = json.load(open(p))
    print(f"\n{f}.json: {jtype(v)}" + (f", keys {list(v)}" if isinstance(v, dict) else ""))
    if has_nul(v): blockers.append(f"{f}.json contains a NUL character")
    if f == "watch_state":
        s = v.get("seen", [])
        print(f"  seen: {len(s)} keys -> emails table")
        if len(s) != len(set(s)): blockers.append(f"watch_state.seen: {len(s) - len(set(s))} duplicate(s) (emails.key is the primary key)")
        if s != sorted(s): notes.append("watch_state.seen is not sorted; rebuilt list will be sorted (same set)")
        if not all(isinstance(x, str) for x in s): blockers.append("watch_state.seen has a non-text key")

print("\n# Result")
for n in notes: print("note:", n)
for b in blockers: print("BLOCKER:", b)
print(f"{len(blockers)} blocker(s), {len(notes)} note(s)")
sys.exit(1 if blockers else 0)
