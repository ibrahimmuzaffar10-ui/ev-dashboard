#!/usr/bin/env python3
"""Schema v2 pass/fail: read everything back through db.py (the same code the website uses) and
compare with the snapshot: same keys, same values, same types (key order ignored, Ibrahim 11/10).
Also proves the check can fail: three planted changes must each be caught. Prints counts only.

  EV_DATA_DIR=<snapshot> .venv/bin/python scripts/verify_v2.py        exit 0 = all pass
"""
import copy, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["EV_BACKEND"] = "supabase"
import db, legacy  # noqa: E402

D = os.path.expanduser(os.environ["EV_DATA_DIR"])
results = []


def check(name, ok, got=""):
    results.append((name, "PASS" if ok else "FAIL", got))


def load(f):
    with open(os.path.join(D, f + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


def diff_items(a, b):
    return sum(legacy.canon(x) != legacy.canon(y) for x, y in zip(a, b)) + abs(len(a) - len(b))


t = load("tracker_data")
want = {k: v for k, v in t.items() if k != "changelog"}
got = db.load()
pays = db.payments()

for k in ("leads", "alerts", "vendors"):
    check(f"{k}: count", len(got[k]) == len(want[k]), f"{len(got[k])} / {len(want[k])}")
    n = diff_items(got[k], want[k])
    check(f"{k}: every item identical (keys, values, types)", n == 0, f"{n} different")
check("tracker_data: identical (minus changelog)", legacy.canon(got) == legacy.canon(want))
check("tracker_data: same top-level key order", list(got) == list(want))
check("payments: identical", legacy.canon(pays) == legacy.canon(load("payments")), f"{len(pays)} items")
for f in ("brief_latest", "brief_state", "brief_ack"):
    check(f"{f}: identical", legacy.canon(db.read_doc(f)) == legacy.canon(load(f)))

# relationships hold and money view works
q = db._read_only(lambda c: c.run("""
  select (select count(*) from public.leads l left join public.clients c using (client_id) where c.client_id is null),
         (select count(*) from public.event_days e left join public.leads l using (lead_id) where l.lead_id is null),
         (select count(*) from public.alerts where lead_id is not null),
         (select count(*) from public.payments where lead_id is not null),
         (select count(*) from public.v_lead_money where mismatch),
         (select count(*) from public.leads where legacy_shape is not null)"""))[0]
check("every lead has a client; every event day has a lead", q[0] == 0 and q[1] == 0)
check("links kept: alerts->leads, payments->leads", q[2] == 13 and q[3] == 17, f"{q[2]} / {q[3]}")
print(f"(info) leads where typed 'paid' differs from installments+payments: {q[4]}  ·  leads with a legacy_shape note: {q[5]}")

# the check must be able to fail
plants = {
    "a total 2500 -> 2500.0": lambda w: next(l for l in w["leads"] if isinstance(l.get("total"), int)).__setitem__("total", float(next(l for l in w["leads"] if isinstance(l.get("total"), int))["total"])),
    "a missing key -> null": lambda w: next(l for l in w["leads"] if "last_contact" not in l).__setitem__("last_contact", None),
    "an event date moved one day": lambda w: next(l for l in w["leads"] if l.get("event")).__setitem__("event", "1999-01-01"),
}
caught = 0
for name, f in plants.items():
    w = copy.deepcopy(want); f(w)
    caught += legacy.canon(got) != legacy.canon(w)
check("planted changes caught", caught == len(plants), f"{caught} / {len(plants)}")

w = max(len(r[0]) for r in results)
for name, res, g in results:
    print(f"{name:<{w}}  {res}  {g}")
fails = sum(r[1] == "FAIL" for r in results)
print(f"\n{len(results) - fails} pass, {fails} fail")
sys.exit(1 if fails else 0)
