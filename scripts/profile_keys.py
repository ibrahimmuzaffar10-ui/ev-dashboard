#!/usr/bin/env python3
"""Schema check against the live JSON. Read-only. Prints key NAMES, types and counts only,
never a value, so the output is safe to paste into chat.

Usage (on the Mac):  EV_DATA_DIR=~/EmanantHQ python3 scripts/profile_keys.py
Exit 0 = every key/type fits schema v1 (or is safely kept in `extra`) and no blockers.
Blockers: duplicate ids/email_ids where the schema says UNIQUE, NUL characters (Postgres can't store them).
"""
import collections, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db_codec as c  # noqa: E402

D = os.path.expanduser(os.environ.get("EV_DATA_DIR", "~/EmanantHQ"))
blockers, notes = [], []


def jtype(v):
    if v is None: return "null"
    if isinstance(v, bool): return "bool"
    if isinstance(v, int): return "int"
    if isinstance(v, float): return "float-whole" if v.is_integer() else "float"
    return {str: "str", list: "list", dict: "dict"}[type(v)]


def has_nul(v):
    return "\x00" in json.dumps(v, ensure_ascii=False).replace("\\u0000", "\x00")


def profile(table, items):
    cols = c.COLUMNS[table]
    keys = collections.defaultdict(collections.Counter)
    orders = collections.Counter()
    for o in items:
        orders[tuple(o)] += 1
        for k, v in o.items():
            keys[k][jtype(v)] += 1
        if has_nul(o): blockers.append(f"{table}: an item contains a NUL character")
    print(f"\n## {table}: {len(items)} items, {len(orders)} distinct key orders")
    print(f"{'key':<16} {'present':>7}  types{'':<30} schema")
    for k in sorted(keys, key=lambda k: -sum(keys[k].values())):
        kind = cols.get(k)
        bad = sum(n for t, n in keys[k].items() if kind and not c._fits(kind, {"null": None, "bool": True, "int": 1, "float": 0.5,
                                                                              "float-whole": 1.0, "str": "", "list": [], "dict": {}}[t]))
        where = "extra (no column)" if not kind else (f"{kind}" + (f"  ⚠ {bad} → extra" if bad else ""))
        print(f"{k:<16} {sum(keys[k].values()):>7}  {dict(keys[k])!s:<35} {where}")
        if not kind: notes.append(f"{table}.{k}: no column, kept in extra ({sum(keys[k].values())} items)")
    missing = [k for k in cols if k not in keys]
    if missing: print("columns never used:", ", ".join(missing))
    return items


def uniq(table, items, key):
    vals = [o.get(key) for o in items if o.get(key) is not None]
    d = len(vals) - len(set(vals))
    if d: blockers.append(f"{table}.{key}: {d} duplicate value(s) but the column is UNIQUE/PK")


t = json.load(open(os.path.join(D, "tracker_data.json")))
print("# tracker_data.json top-level keys:", list(t))
for k in t:
    if k not in ("leads", "alerts", "vendors", "changelog"): print(f"  {k}: {jtype(t[k])} → app_state")
uniq("leads", profile("leads", t.get("leads", [])), "id")
A = profile("alerts", t.get("alerts", [])); uniq("alerts", A, "id"); uniq("alerts", A, "email_id")
profile("vendors", t.get("vendors", []))
profile("changelog", t.get("changelog", []))
pp = os.path.join(D, "payments.json")
if os.path.exists(pp): uniq("payments", profile("payments", json.load(open(pp))), "email_id")
for f in ("watch_state", "brief_latest", "brief_state", "brief_ack"):
    p = os.path.join(D, f + ".json")
    if not os.path.exists(p): print(f"\n{f}.json: not found"); continue
    v = json.load(open(p))
    print(f"\n{f}.json: {jtype(v)}" + (f", keys {list(v)}" if isinstance(v, dict) else ""))
    if f == "watch_state":
        s = v.get("seen", [])
        print(f"  seen: {len(s)} keys, {len(s) - len(set(s))} duplicates")
        if len(s) != len(set(s)): blockers.append("watch_state.seen has duplicates (seen_emails.key is the PK)")
    if has_nul(v): blockers.append(f"{f}.json contains a NUL character")

print("\n# Result")
for n in notes: print("note:", n)
for b in blockers: print("BLOCKER:", b)
print(f"{len(blockers)} blocker(s), {len(notes)} key(s) going to extra")
sys.exit(1 if blockers else 0)
