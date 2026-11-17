#!/usr/bin/env python3
"""Phase 8 pass/fail: the watcher's quick check may only say "nothing new" when a full run would
truly have nothing to do. Fake mailbox (no iCloud, no Supabase, no posts); prints PASS/FAIL only.

  .venv/bin/python scripts/test_step8.py          (expect 20/20)
"""
import datetime, json, os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="ev-step8-")
os.environ.update(EV_WATCH_QUICK="1", EV_WATCH_CACHE=os.path.join(TMP, "cache.json"), EV_BACKEND="json", EV_ALLOW_JSON="1", EV_DATA_DIR=TMP)
import watch, evtime  # noqa: E402

results = []
def check(name, ok, got=""): results.append((name, "PASS" if ok else "FAIL", str(got)))

BOX = {}
def fake_search(mailbox, since, **kw):
    v = BOX[mailbox]
    if isinstance(v, Exception): raise v
    return [dict(e) for e in v]
watch.search_all = fake_search

def env(i, mid=True, seen=True):
    return {"id": str(i), "message-id": f"<m{i}@x>" if mid else None, "flags": [{"iana": "seen"}] if seen else []}

def reset():
    BOX.update({"Inbox": [env(1), env(2, seen=False), env(3, mid=False)], "Junk": [env(4)], "Sent Messages": [env(5)]})

class FakeS:   # what State looks like after a full run saved to Supabase
    def __init__(self, rows): self.rows = rows
    def seen(self, k): return watch.State.seen(self, k)

NOW = evtime.now_ct().replace(hour=14, minute=0, second=0, microsecond=0)
def full_rows():
    return {"<m1@x>": ("processed", 0), "<m2@x>": ("skipped", 0), "inbox:3": ("processed", 0),
            "<m4@x>": ("skipped", 0), "sent:<m5@x>": ("processed", 0)}
def write(rows=None, ok=True, last=None, flags="auto", since="2026-11-14"):
    envs = BOX["Inbox"] + [dict(j, junk=True) for j in BOX["Junk"]]
    watch.write_cache(FakeS(rows or full_rows()), since, watch.unread_flags(envs) if flags == "auto" else flags, ok)
    c = json.load(open(watch.CACHE_PATH)); c["last_full"] = (last or NOW - datetime.timedelta(minutes=10)).isoformat(timespec="seconds")
    json.dump(c, open(watch.CACHE_PATH, "w"))
q = lambda now=NOW: watch.quick_check(now)

reset(); watch.drop_cache()
check("1. no cache -> full run", q() == "no cache", q())
open(watch.CACHE_PATH, "w").write("{not json")
check("2. corrupt cache -> full run", q() == "no cache", q())
reset(); write()
check("3. nothing new -> quick stop", q() == "", repr(q()))
BOX["Inbox"].append(env(9))
check("4. new Inbox email -> full", q() == "new mail", q())
reset(); write(); BOX["Junk"].append(env(10))
check("5. new Junk email -> full", q() == "new mail", q())
reset(); write(); BOX["Inbox"].append(env(11, mid=False))
check("6. new email without Message-ID -> full", q() == "new mail", q())
reset(); write(); BOX["Sent Messages"].append(env(12))
check("7. new Sent email (Eman replied) -> full", q() == "new sent mail", q())
reset(); write(); BOX["Inbox"][1]["flags"] = [{"iana": "seen"}]
check("8. read/unread changed -> full", q() == "read/unread changed", q())
reset(); r = full_rows(); r["<m1@x>"] = ("failed", 1); write(rows=r)
check("9. email waiting for a retry -> full", q() == "new mail", q())
reset(); r = full_rows(); r["<m1@x>"] = ("failed", watch.MAX_TRIES); write(rows=r)
check("10. gave up after 3 tries (person alerted) -> no rerun", q() == "", repr(q()))
reset(); write(ok=False)
check("11. last full run had failures -> full", q() == "last full run had failures", q())
reset(); write(last=NOW - datetime.timedelta(hours=13))
check("12. over 12 h since full run -> full", q().startswith("last full run over 12 h"), q())
reset(); write(last=NOW + datetime.timedelta(hours=1))
check("13. cache from the future (clock moved) -> full", q().startswith("last full run over 12 h"), q())
reset(); write(last=NOW.replace(hour=20, minute=50))
check("14. 9 PM end-of-day sweep -> full", q(NOW.replace(hour=21, minute=1)) == "scheduled sweep 21:00", q(NOW.replace(hour=21, minute=1)))
reset(); write(last=NOW.replace(hour=6, minute=40))
check("15. 6:45 AM sweep (sign-by reminders) -> full", q(NOW.replace(hour=6, minute=46)) == "scheduled sweep 06:45", q(NOW.replace(hour=6, minute=46)))
reset(); write(last=NOW.replace(hour=21, minute=2))
check("16. sweep not repeated after it ran", q(NOW.replace(hour=21, minute=30)) == "", repr(q(NOW.replace(hour=21, minute=30))))
reset(); write(); BOX["Junk"] = RuntimeError("imap down")
check("17. mailbox unreachable -> full (never 'nothing new')", q().startswith("mailbox check failed"), q())
reset(); write(flags=None)
check("18. unread sync failed last time -> full", q() == "read/unread changed", q())
reset(); r = full_rows(); del r["inbox:3"]; r["3"] = ("processed", 0); write(rows=r)
check("19. old bare-id key still counts as seen (like the full run)", q() == "", repr(q()))
reset(); write(); c = json.load(open(watch.CACHE_PATH)); c["v"] = 0; json.dump(c, open(watch.CACHE_PATH, "w"))
check("20. cache from another version -> full", q() == "cache unreadable", q())

import shutil; shutil.rmtree(TMP, ignore_errors=True)
w = max(len(r[0]) for r in results)
for n, res, got in results: print(f"{n:<{w}}  {res}  {got[:70]}")
fails = sum(r[1] == "FAIL" for r in results)
print(f"\n{len(results) - fails} pass, {fails} fail")
sys.exit(1 if fails else 0)
