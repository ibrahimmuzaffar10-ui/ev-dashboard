#!/usr/bin/env python3
"""Phase 3 pass/fail: rebuild every JSON file FROM SUPABASE and compare it to the snapshot.
Prints counts and PASS/FAIL only, never a value.

  EV_DATA_DIR=<snapshot> python3 scripts/verify_migration.py      exit 0 = all pass

Checks
 1. Row counts per table = item counts in the snapshot.
 2. Every stored `raw` text is byte-identical to what migrate_data.py sent (exact storage).
 3. Each file rebuilt from the tables (the future load()) equals the snapshot exactly: compared
    as JSON text without key sorting, so key order, missing-vs-null, 500 vs 500.0, true vs 1
    all count. tracker_data is compared without the dropped changelog.
 4. Generated (searchable) columns: ids never NULL, and NULL counts match the snapshot types.
"""
import json, os, subprocess, sys

D = os.path.expanduser(os.environ["EV_DATA_DIR"])
TABLE_LISTS = ("leads", "vendors", "alerts")
results = []


def j(v):
    return json.dumps(v, ensure_ascii=False, allow_nan=False)


def q(sql):
    p = subprocess.run(["supabase", "db", "query", "--linked", sql], capture_output=True, text=True)
    s = p.stdout
    if p.returncode != 0 or "{" not in s:
        sys.exit(f"query failed (exit {p.returncode}): {p.stderr[-300:]}")
    obj, _ = json.JSONDecoder().raw_decode(s[s.index("{"):])
    return obj["rows"]


def check(name, ok, got=""):
    results.append((name, "PASS" if ok else "FAIL", got))


def load(f):
    with open(os.path.join(D, f + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


snap = {f: load(f) for f in ("tracker_data", "payments", "watch_state", "brief_latest", "brief_state", "brief_ack")}
t = snap["tracker_data"]
want = {"leads": t["leads"], "vendors": t["vendors"], "alerts": t["alerts"], "payments": snap["payments"]}

# 1 + 2: rows, counts, exact raw text
got = {}
for table, items in want.items():
    rows = q(f"select pos, raw::text as r from public.{table} order by pos")
    got[table] = [json.loads(r["r"]) for r in rows]
    check(f"{table}: row count", len(rows) == len(items), f"{len(rows)} / {len(items)}")
    check(f"{table}: positions 0..n-1", [r["pos"] for r in rows] == list(range(len(items))))
    same = sum(1 for r, o in zip(rows, items) if r["r"] == j(o))
    check(f"{table}: stored text identical", same == len(items), f"{same} / {len(items)}")

emails = [r["key"] for r in q("select key from public.emails where status <> 'pending' order by key collate \"C\"")]
seen = snap["watch_state"].get("seen", [])
check("emails: row count", len(emails) == len(seen), f"{len(emails)} / {len(seen)}")

state = {}
for r in q("select doc, key, value::text as v from public.app_state"):
    state.setdefault(r["doc"], {})[r["key"]] = json.loads(r["v"])


def rebuild(doc, lists):
    s = state.get(doc, {})
    if "" in s and "_key_order" not in s:
        return s[""]
    return {k: (lists[k] if k in lists else s[k]) for k in s.get("_key_order", [])}


# 3: the future load(): rebuilt files vs snapshot
t_want = {k: v for k, v in t.items() if k != "changelog"}
t_got = rebuild("tracker_data", {k: got[k] for k in TABLE_LISTS})
check("tracker_data.json rebuilt = snapshot (minus changelog)", j(t_got) == j(t_want))
check("payments.json rebuilt = snapshot", j(got["payments"]) == j(snap["payments"]))
ws_got = rebuild("watch_state", {"seen": emails[-3000:]})
check("watch_state.json rebuilt = snapshot", j(ws_got) == j(snap["watch_state"]))
for f in ("brief_latest", "brief_state", "brief_ack"):
    check(f"{f}.json rebuilt = snapshot", j(rebuild(f, {})) == j(snap[f]))

# 4: generated columns behave
def nulls(table, col):
    return q(f"select count(*) as n from public.{table} where {col} is null")[0]["n"]

check("leads.id never NULL", nulls("leads", "id") == 0)
check("alerts.id never NULL", nulls("alerts", "id") == 0)
check("payments.email_id never NULL", nulls("payments", "email_id") == 0)
for table, col, typ in (("leads", "total", (int, float)), ("leads", "paid", (int, float)), ("leads", "status", str),
                        ("payments", "amount", (int, float)), ("alerts", "done", bool), ("alerts", "lead_id", str)):
    exp = sum(1 for o in want[table] if not (isinstance(o.get(col), typ) and (typ is bool) == isinstance(o.get(col), bool)))
    n = nulls(table, col)
    check(f"{table}.{col} NULLs match the data", n == exp, f"{n} / {exp}")

w = max(len(r[0]) for r in results)
for name, res, g in results:
    print(f"{name:<{w}}  {res}  {g}")
fails = sum(r[1] == "FAIL" for r in results)
print(f"\n{len(results) - fails} pass, {fails} fail")
sys.exit(1 if fails else 0)
