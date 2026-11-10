#!/usr/bin/env python3
"""Step 2 pass/fail: the Mac jobs (watcher, Zelle import, brief) on Supabase.
Read-only on the mailbox; SHADOW mode (no pop-ups, no Zelle run from the watcher, no email); saves go
through a test server on :8789 whose documents folder is the scratch dir. Supabase is reloaded from
the snapshot at the end and checked exact. Prints counts and PASS/FAIL only.

  .venv/bin/python scripts/test_step2.py <scratch dir with snap/>      exit 0 = all pass
"""
import datetime, fcntl, json, os, socket, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["EV_BACKEND"] = "supabase"
import db  # noqa: E402

SCRATCH = sys.argv[1]
SNAP = os.path.join(SCRATCH, "snap")
PY = sys.executable
results, procs = [], []
YDAY = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()


def check(name, ok, got=""):
    results.append((name, "PASS" if ok else "FAIL", got))


def start(port, backend, data_dir):
    env = dict(os.environ, EV_BACKEND=backend, EV_PORT=str(port), EV_DATA_DIR=data_dir, EV_DOCS_DIR=os.path.join(SCRATCH, "docs"))
    procs.append(subprocess.Popen([PY, os.path.join(ROOT, "server.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close(); return
        except OSError:
            time.sleep(0.1)
    raise SystemExit(f"server on {port} did not start")


def run(script, backend="supabase", api="http://127.0.0.1:8789", data_dir=SNAP, extra=None, args=()):
    env = dict(os.environ, EV_BACKEND=backend, EV_SHADOW="1", EV_API=api, EV_DATA_DIR=data_dir,
               EV_WATCH_LOCK=os.path.join(SCRATCH, f"watch-{backend}.lock"), **(extra or {}))
    p = subprocess.run([PY, os.path.join(ROOT, script), *args], env=env, capture_output=True, text=True, timeout=900)
    return p.returncode, p.stdout + p.stderr


def q(sql, **kw):
    return db._read_only(lambda c: c.run(sql, **kw))


def w(sql, **kw):
    c = db._connect()
    try:
        c.run("begin"); c.run(sql, **kw); c.run("commit")
    finally:
        c.close()


def recent_mids():
    since = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
    r = subprocess.run(["himalaya", "--json", "envelope", "search", "-s", "50", f"after {since} order by date asc"],
                       capture_output=True, text=True, timeout=300)
    return [e["message-id"] for e in json.loads(r.stdout)["envelopes"] if e.get("message-id")]


def emails(keys):
    return {k: (s, a) for k, s, a in q("select key, status, attempts from public.emails where key = any(cast(:k as text[]))", k=keys)}


def watch_meta():
    return db.read_doc("watch_state") or {}


try:
    start(8789, "supabase", SNAP)
    mids = recent_mids()
    present = list(emails(mids))[:6]
    check("setup: recent emails found in Supabase", len(present) > 0, f"{len(present)} (of {len(mids)} in the last 3 days)")
    alerts_before = q("select count(*) from public.alerts")[0][0]
    meta0 = watch_meta()

    # ---- A. server down: nothing may be lost
    w("delete from public.emails where key = any(cast(:k as text[]))", k=present)
    rc, out = run("watch.py", extra={"EV_TEST_FAIL_POSTS": "1"})
    st = emails(present)
    failed = [k for k, v in st.items() if v[0] == "failed"]
    check("A. server down: no email marked handled by mistake", all(v[0] in ("failed", "skipped") for v in st.values()) and len(st) == len(present),
          f"{len(failed)} failed (will retry), {sum(v[0] == 'skipped' for v in st.values())} skipped (needed no save)")
    check("A. server down: last good run NOT moved forward", (not failed) or watch_meta().get("last_ok") == meta0.get("last_ok"))
    check("A. server down: no alert created", q("select count(*) from public.alerts")[0][0] == alerts_before)

    # ---- B. server back: retried and handled, no duplicates
    rc, out = run("watch.py")
    st = emails(present)
    check("B. back up: every email now handled", all(v[0] in ("processed", "skipped") for v in st.values()), out.strip().splitlines()[-1][:80] if out.strip() else "")
    dups = q("select count(*) from (select email_key from public.alert_emails where email_key = any(cast(:k as text[])) group by email_key having count(*) > 1) x", k=present)[0][0]
    check("B. back up: 0 duplicate alerts for those emails", dups == 0)
    check("B. back up: last good run = yesterday", watch_meta().get("last_ok") == YDAY, watch_meta().get("last_ok"))

    # ---- C. run again: nothing new
    a1 = q("select count(*) from public.alerts")[0][0]
    rc, out = run("watch.py")
    check("C. second run changes nothing", q("select count(*) from public.alerts")[0][0] == a1 and ", 0 alerts" in out, out.strip().splitlines()[-1][:80] if out.strip() else "")

    # ---- D. never gives up silently: at the 3rd failure it must alert a person first
    if failed:
        k = failed[0]
        w("update public.emails set status = 'failed', attempts = 2 where key = :k", k=k)
        rc, out = run("watch.py", extra={"EV_TEST_FAIL_POSTS": "1"})
        check("D. 3rd failure + alert impossible -> keeps retrying (not dropped)", emails([k]).get(k) == ("failed", 2), str(emails([k]).get(k)))
        w("update public.emails set status = 'processed', attempts = 0 where key = :k", k=k)
    else:
        check("D. give-up path", True, "skipped: no recent email needed a save")

    # ---- E. one run at a time
    lock = open(os.path.join(SCRATCH, "watch-supabase.lock"), "w"); fcntl.flock(lock, fcntl.LOCK_EX)
    rc, out = run("watch.py")
    fcntl.flock(lock, fcntl.LOCK_UN); lock.close()
    check("E. overlapping run is refused", "another run is still going" in out)

    # ---- F. Zelle import on Supabase: idempotent, no duplicates
    n0 = q("select count(*) from public.payments")[0][0]
    rc1, out1 = run("zelle_import.py")
    rc2, out2 = run("zelle_import.py")
    n2 = q("select count(*) from public.payments")[0][0]
    new1 = out1.strip().splitlines()[-1] if out1.strip() else out1
    check("F. Zelle import runs on Supabase", rc1 == 0 and rc2 == 0, new1[:60] if rc1 == 0 else out1[-160:])
    check("F. second import adds nothing", out2.strip().endswith(f"0 new, {n2} total"), f"{n0} -> {n2}")
    ids = db.read_doc("zelle_ids") or {}
    check("F. permanent ids remembered for older payments", len(ids) > 0, f"{len(ids)} mapped")

    # ---- G. brief on Supabase shows up on the dashboard
    rc, out = run("brief.py", args=("--force",))
    latest = db.read_doc("brief_latest") or {}
    import urllib.request
    shown = json.load(urllib.request.urlopen("http://127.0.0.1:8789/api/brief", timeout=30)).get("brief") or {}
    check("G. brief written to Supabase and served", rc == 0 and latest.get("id") and shown.get("id") == latest.get("id"), latest.get("id", out[-120:]))

    # ---- H. JSON-file mode keeps working (local fallback), same retry rules
    work = os.path.join(SCRATCH, "work")
    subprocess.run(["rm", "-rf", work]); subprocess.run(["cp", "-R", SNAP, work], check=True)
    start(8790, "json", work)
    stp = os.path.join(work, "watch_state.json")
    stj = json.load(open(stp)); drop = [k for k in present if k in stj["seen"]]
    stj["seen"] = [k for k in stj["seen"] if k not in drop]; json.dump(stj, open(stp, "w"))
    rc, out = run("watch.py", backend="json", api="http://127.0.0.1:8790", data_dir=work, extra={"EV_TEST_FAIL_POSTS": "1"})
    s1 = json.load(open(stp))
    rc, out = run("watch.py", backend="json", api="http://127.0.0.1:8790", data_dir=work)
    s2 = json.load(open(stp))
    check("H. JSON mode: failures kept for retry, then handled", all(k in s2["seen"] for k in drop) and not s2.get("retry")
          and (not set(s1.get("retry", {})) or all(k not in s1["seen"] for k in s1.get("retry", {}))), f"{len(s1.get('retry', {}))} retried")
finally:
    for p in procs:
        p.terminate()
    for p in procs:
        p.wait(10)
    # ---- restore Supabase to the snapshot and prove it exact
    env = dict(os.environ, EV_DATA_DIR=SNAP)
    r1 = subprocess.run([PY, os.path.join(ROOT, "scripts", "migrate_v2.py")], env=env, capture_output=True, text=True)
    r2 = subprocess.run([PY, os.path.join(ROOT, "scripts", "verify_v2.py")], env=env, capture_output=True, text=True)
    check("cleanup: Supabase reloaded from the snapshot and verified exact", r1.returncode == 0 and r2.returncode == 0, r2.stdout.strip().splitlines()[-1] if r2.stdout.strip() else r1.stderr[-160:])

width = max(len(r[0]) for r in results)
for name, res, got in results:
    print(f"{name:<{width}}  {res}  {got}")
fails = sum(r[1] == "FAIL" for r in results)
print(f"\n{len(results) - fails} pass, {fails} fail")
sys.exit(1 if fails else 0)
