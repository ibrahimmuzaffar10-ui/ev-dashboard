#!/usr/bin/env python3
"""Step 3 pass/fail: the email outbox. NOTHING is sent: the Mac sender runs with EV_OUTBOX_DRY
(writes .eml files to the scratch dir). Saves go through a test server on :8789. Supabase is
reloaded from the snapshot afterwards and checked exact. Prints counts and PASS/FAIL only.

  .venv/bin/python scripts/test_step3.py <scratch dir with snap/>     exit 0 = all pass
"""
import email, fcntl, hashlib, json, os, socket, subprocess, sys, time, urllib.request
from email import policy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["EV_BACKEND"] = "supabase"
import db, evenv  # noqa: E402

SCRATCH = sys.argv[1]
SNAP, DRY = os.path.join(SCRATCH, "snap"), os.path.join(SCRATCH, "outbox-dry")
PY = sys.executable
results, procs = [], []
FE = "test-3@example.invalid"  # leak-check: allow: fake .invalid test address
MID = "<TEST-3-e1@example.invalid>"  # leak-check: allow: fake Message-ID on the .invalid TLD


def check(name, ok, got=""):
    results.append((name, "PASS" if ok else "FAIL", got))


def http(path, body):
    req = urllib.request.Request("http://127.0.0.1:8789" + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:120]


def q(sql, **kw):
    return db._read_only(lambda c: c.run(sql, **kw))


def w(sql, **kw):
    c = db._connect()
    try:
        c.run("begin"); c.run(sql, **kw); c.run("commit")
    finally:
        c.close()


def sender(dry=DRY):
    env = dict(os.environ, EV_BACKEND="supabase", EV_API="http://127.0.0.1:8789", EV_OUTBOX_DRY=dry,
               EV_OUTBOX_LOCK=os.path.join(SCRATCH, "outbox.lock"))
    p = subprocess.run([PY, os.path.join(ROOT, "outbox_send.py")], env=env, capture_output=True, text=True, timeout=300)
    return p.returncode, (p.stdout + p.stderr).strip()


try:
    env = dict(os.environ, EV_BACKEND="supabase", EV_PORT="8789", EV_DATA_DIR=SNAP, EV_DOCS_DIR=os.path.join(SCRATCH, "docs"))
    procs.append(subprocess.Popen([PY, os.path.join(ROOT, "server.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    for _ in range(100):
        try: socket.create_connection(("127.0.0.1", 8789), 0.2).close(); break
        except OSError: time.sleep(0.1)
    check("setup: outbox empty", q("select count(*) from public.outbox")[0][0] == 0)

    # ---- A. a reply to a client is queued inside the same save
    st, r = http("/api/alert-new", {"email_id": MID, "from_email": FE, "type": "email", "title": "TEST 3 alert", "detail": "TEST"})
    aid = r["alert"]["id"] if st == 200 else None
    st, r = http("/api/send-reply", {"id": aid, "subject": "Re: TEST", "body": "Thanks for reaching out, this is a TEST reply."})
    rows = q("select outbox_id, to_addr, in_reply_to, status from public.outbox")
    check("A. reply route OK and email queued", st == 200 and len(rows) == 1 and rows[0][3] == "queued", f"HTTP {st}, {len(rows)} queued")
    check("A. queued to the client, threaded as a reply", rows and rows[0][1] == FE and rows[0][2] == MID)
    alert_row = q("select awaiting_reply, done from public.alerts where alert_id = :a", a=aid)
    check("A. the save happened too (alert marked replied)", alert_row and alert_row[0] == [True, True])

    # ---- B. no save -> no email (refused request, and a rolled-back save)
    st, r = http("/api/send-reply", {"id": aid, "subject": "Re: TEST", "body": "too short"})
    n = q("select count(*) from public.outbox")[0][0]
    import threading
    try:
        with db.locked(threading.Lock()):
            db.load(); db.outbox_enqueue(FE, "TEST rolled back", "should never exist")
            raise RuntimeError("simulated failure before the save")
    except RuntimeError:
        pass
    check("B. refused request queues nothing; failed save queues nothing", st == 400 and n == 1 and q("select count(*) from public.outbox")[0][0] == 1)

    # ---- C. email to Eman herself, with attachments
    pdf = b"%PDF-1.4 TEST attachment\n" * 40
    mid_self = db.outbox_enqueue("self", "[Emanant HQ] TEST notice", "TEST body", None, [("TEST.pdf", "application/pdf", pdf)])

    # ---- D. the Mac sender (dry run)
    rc, out = sender()
    sent = q("select outbox_id, message_id, status from public.outbox order by outbox_id")
    check("D. sender sent both", rc == 0 and all(s == "sent" for _, _, s in sent), out.splitlines()[-1] if out else "")
    msgs = {}
    for oid, mid, _ in sent:
        p = os.path.join(DRY, f"{oid}.eml")
        if os.path.exists(p):
            msgs[mid] = email.message_from_bytes(open(p, "rb").read(), policy=policy.default)
    reply = next((m for k, m in msgs.items() if k != mid_self), None)
    note = msgs.get(mid_self)
    check("D. reply: same Message-ID as queued, In-Reply-To kept, to the client",
          reply is not None and reply["In-Reply-To"] == MID and reply["To"] == FE)
    att = next(note.iter_attachments(), None) if note else None
    check("D. 'self' becomes Eman's address; attachment byte-identical",
          note is not None and note["To"] == evenv.need("EV_FROM_EMAIL") and att is not None
          and hashlib.sha256(att.get_content()).hexdigest() == hashlib.sha256(pdf).hexdigest())

    # ---- E. sending fails -> retry later, then give up with an alert (never silently)
    db.outbox_enqueue(FE, "TEST will fail", "TEST")
    rc, out = sender(dry="/dev/null/cannot-write")
    st1 = q("select status, attempts, next_try_at > now() from public.outbox where subject = 'TEST will fail'")[0]
    rc, out = sender(dry="/dev/null/cannot-write")
    st2 = q("select status, attempts from public.outbox where subject = 'TEST will fail'")[0]
    check("E. failure -> queued again with a wait (not retried immediately)", st1 == ["queued", 1, True] and st2 == ["queued", 1], f"{st1} / {st2}")
    w("update public.outbox set attempts = 4, next_try_at = now() where subject = 'TEST will fail'")
    rc, out = sender(dry="/dev/null/cannot-write")
    oid = q("select outbox_id, status from public.outbox where subject = 'TEST will fail'")[0]
    alerted = q("select count(*) from public.alert_emails where email_key = :k", k=f"outbox-failed:{oid[0]}")[0][0]
    check("E. 5th failure -> 'failed' + a dashboard alert", oid[1] == "failed" and alerted == 1)

    # ---- F. interrupted send is never re-sent
    db.outbox_enqueue(FE, "TEST interrupted", "TEST")
    w("update public.outbox set status = 'sending', claimed_at = now() - interval '20 minutes', attempts = 1 where subject = 'TEST interrupted'")
    before = set(os.listdir(DRY))
    rc, out = sender()
    row = q("select outbox_id, status from public.outbox where subject = 'TEST interrupted'")[0]
    alerted = q("select count(*) from public.alert_emails where email_key = :k", k=f"outbox-unknown:{row[0]}")[0][0]
    check("F. interrupted -> 'unknown' + alert, not re-sent", row[1] == "unknown" and alerted == 1 and set(os.listdir(DRY)) == before)

    # ---- G. one sender at a time
    lock = open(os.path.join(SCRATCH, "outbox.lock"), "w"); fcntl.flock(lock, fcntl.LOCK_EX)
    rc, out = sender()
    fcntl.flock(lock, fcntl.LOCK_UN); lock.close()
    check("G. overlapping sender refused", "another run is still going" in out)
finally:
    for p in procs:
        p.terminate()
    for p in procs:
        p.wait(10)
    try:
        w("delete from public.outbox")
    except Exception as ex:
        print("outbox cleanup failed:", ex)
    env = dict(os.environ, EV_DATA_DIR=SNAP)
    r1 = subprocess.run([PY, os.path.join(ROOT, "scripts", "migrate_v2.py")], env=env, capture_output=True, text=True)
    r2 = subprocess.run([PY, os.path.join(ROOT, "scripts", "verify_v2.py")], env=env, capture_output=True, text=True)
    check("cleanup: outbox emptied; Supabase reloaded from the snapshot and verified exact",
          r1.returncode == 0 and r2.returncode == 0 and q("select count(*) from public.outbox")[0][0] == 0,
          r2.stdout.strip().splitlines()[-1] if r2.stdout.strip() else r1.stderr[-160:])

width = max(len(r[0]) for r in results)
for name, res, got in results:
    print(f"{name:<{width}}  {res}  {got}")
fails = sum(r[1] == "FAIL" for r in results)
print(f"\n{len(results) - fails} pass, {fails} fail")
sys.exit(1 if fails else 0)
