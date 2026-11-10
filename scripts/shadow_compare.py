#!/usr/bin/env python3
"""Step 5: compare the 48 h shadow run (Supabase) with the live system (JSON files on the Mac).

  .venv/bin/python scripts/shadow_compare.py start     record the starting point (run right after reloading Supabase)
  .venv/bin/python scripts/shadow_compare.py report    compare everything that arrived since the start

Compares what both sides did with the SAME incoming mail, at the level that does not depend on
manual edits (which happen only in the live dashboard during the shadow run):
  1. emails handled (Message-ID keys)            -> must match exactly
  2. emails that produced an alert, and its type -> must match exactly
  3. new leads (by sender address)               -> must match exactly
  4. new Zelle payments (date, amount, sender)   -> must match exactly
Differences caused by manual live edits (e.g. an alert closed in the live dashboard, so a later email
merged differently) are listed separately as "explained". Prints counts and keys' hashes, no values.
The start file holds email keys/addresses: it lives in ~/Library/Application Support/emanant-hq and
is deleted by `report --done`.
"""
import collections, hashlib, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["EV_BACKEND"] = "supabase"
import db  # noqa: E402

LIVE = os.path.expanduser("~/EmanantHQ")
START = os.path.expanduser("~/Library/Application Support/emanant-hq/shadow-start.json")


def live_state():
    t = json.load(open(os.path.join(LIVE, "tracker_data.json")))
    ws = json.load(open(os.path.join(LIVE, "watch_state.json")))
    pays = json.load(open(os.path.join(LIVE, "payments.json")))
    alerts = {}
    for a in t.get("alerts", []):
        for k in [a.get("email_id")] + list(a.get("email_ids") or []):
            if k: alerts[k] = a.get("type")
    return {"seen": sorted(ws.get("seen", [])), "alerts": alerts,
            "leads": sorted({(l.get("src_email") or "").lower() for l in t["leads"] if l.get("src_email")}),
            "pays": sorted({f"{p['date']}|{p['amount']}|{p.get('sender', '')}" for p in pays})}


def cloud_state():
    d = db.load()
    rows = db.email_rows()
    alerts = {}
    for a in d.get("alerts", []):
        for k in [a.get("email_id")] + list(a.get("email_ids") or []):
            if k: alerts[k] = a.get("type")
    return {"seen": sorted(k for k, (s, n) in rows.items() if s in ("processed", "skipped") or (s == "failed" and n >= 3)),
            "pending": sorted(k for k, (s, n) in rows.items() if s == "failed" and n < 3),
            "alerts": alerts,
            "leads": sorted({(l.get("src_email") or "").lower() for l in d["leads"] if l.get("src_email")}),
            "pays": sorted({f"{p['date']}|{p['amount']}|{p.get('sender', '')}" for p in db.payments_all()})}


def h(x):
    return hashlib.sha256(x.encode()).hexdigest()[:10]


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "start":
        os.makedirs(os.path.dirname(START), exist_ok=True)
        fd = os.open(START, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump({"live": live_state(), "cloud": cloud_state()}, fh)
        print("shadow start recorded")
        return
    if cmd != "report":
        sys.exit(__doc__)
    s = json.load(open(START))
    L, C = live_state(), cloud_state()
    new = lambda now, then: set(now) - set(then)
    rows = []

    def cmp(name, live_new, cloud_new):
        only_l, only_c = live_new - cloud_new, cloud_new - live_new
        rows.append((name, len(live_new), len(cloud_new), len(only_l), len(only_c)))
        return only_l, only_c

    # real Message-IDs (no angle brackets in this mailbox) contain '@'; mailbox-number fallbacks don't
    mid = lambda ks: {k for k in ks if "@" in k.split("sent:", 1)[-1]}
    cmp("emails handled (Message-ID keys)", mid(new(L["seen"], s["live"]["seen"])), mid(new(C["seen"], s["cloud"]["seen"])))
    la = {k: v for k, v in L["alerts"].items() if k not in s["live"]["alerts"]}
    ca = {k: v for k, v in C["alerts"].items() if k not in s["cloud"]["alerts"]}
    cmp("emails that produced an alert", set(la), set(ca))
    cmp("same alert type", {f"{k}|{v}" for k, v in la.items()}, {f"{k}|{v}" for k, v in ca.items()})
    cmp("new leads (sender address)", new(L["leads"], s["live"]["leads"]), new(C["leads"], s["cloud"]["leads"]))
    cmp("new Zelle payments", new(L["pays"], s["live"]["pays"]), new(C["pays"], s["cloud"]["pays"]))
    width = max(len(r[0]) for r in rows)
    print(f"{'check':<{width}}  live  cloud  only-live  only-cloud")
    for name, l, c, ol, oc in rows:
        print(f"{name:<{width}}  {l:>4}  {c:>5}  {ol:>9}  {oc:>10}  {'PASS' if ol == oc == 0 else 'FAIL'}")
    print(f"emails still being retried in the cloud: {len(C['pending'])}")
    fails = sum(1 for r in rows if r[3] or r[4])
    print(f"\n{len(rows) - fails} pass, {fails} fail")
    if "--done" in sys.argv:
        os.remove(START); print("start file deleted")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
