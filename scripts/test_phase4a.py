#!/usr/bin/env python3
"""Phase 4a pass/fail: the server on Supabase behaves exactly like the server on JSON files.
Uses TEST records only, sends no email, never writes to ~/EmanantHQ, and leaves Supabase exactly
as it found it (checked). Prints counts and PASS/FAIL only.

  .venv/bin/python scripts/test_phase4a.py <scratch dir>        exit 0 = all pass

Precondition: Supabase holds the same data as <scratch>/snap (run migrate_data.py on that snapshot).
"""
import concurrent.futures as cf, datetime, hashlib, json, os, socket, subprocess, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import evtime  # noqa: E402
import legacy  # noqa: E402


def same(x, y):
    """Same HTTP status and same content: JSON compared as data (key order ignored, Ibrahim 11/10)."""
    if x[0] != y[0]:
        return False
    try:
        return legacy.canon(json.loads(x[1])) == legacy.canon(json.loads(y[1]))
    except ValueError:
        return x[1] == y[1]

SCRATCH = sys.argv[1]
SNAP = os.path.join(SCRATCH, "snap")
PY = sys.executable
results, procs = [], []


def check(name, ok, got=""):
    results.append((name, "PASS" if ok else "FAIL", got))


def start(port, backend, data_dir, tz=None):
    env = dict(os.environ, EV_BACKEND=backend, EV_PORT=str(port), EV_DATA_DIR=data_dir,
               EV_DOCS_DIR=os.path.join(SCRATCH, "docs"))     # never the real Documents folder
    if tz:
        env["TZ"] = tz
    p = subprocess.Popen([PY, os.path.join(ROOT, "server.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    procs.append(p)
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close(); return
        except OSError:
            time.sleep(0.1)
    raise SystemExit(f"server on {port} did not start")


def http(port, path, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def db_dump():
    """Every row of every data table (minus timestamps), as one fingerprint per table (no values printed)."""
    sql = "select 'clients' t, coalesce(string_agg((to_jsonb(x) - 'created_at' - 'updated_at')::text, E'\\n' order by (to_jsonb(x) - 'created_at' - 'updated_at')::text), '') s from public.clients x union all select 'leads' t, coalesce(string_agg((to_jsonb(x) - 'created_at' - 'updated_at')::text, E'\\n' order by (to_jsonb(x) - 'created_at' - 'updated_at')::text), '') s from public.leads x union all select 'event_days' t, coalesce(string_agg((to_jsonb(x) - 'created_at' - 'updated_at')::text, E'\\n' order by (to_jsonb(x) - 'created_at' - 'updated_at')::text), '') s from public.event_days x union all select 'contracts' t, coalesce(string_agg((to_jsonb(x) - 'created_at' - 'updated_at')::text, E'\\n' order by (to_jsonb(x) - 'created_at' - 'updated_at')::text), '') s from public.contracts x union all select 'contract_plan_items' t, coalesce(string_agg((to_jsonb(x) - 'created_at' - 'updated_at')::text, E'\\n' order by (to_jsonb(x) - 'created_at' - 'updated_at')::text), '') s from public.contract_plan_items x union all select 'documents' t, coalesce(string_agg((to_jsonb(x) - 'created_at' - 'updated_at')::text, E'\\n' order by (to_jsonb(x) - 'created_at' - 'updated_at')::text), '') s from public.documents x union all select 'installments' t, coalesce(string_agg((to_jsonb(x) - 'created_at' - 'updated_at')::text, E'\\n' order by (to_jsonb(x) - 'created_at' - 'updated_at')::text), '') s from public.installments x union all select 'payments' t, coalesce(string_agg((to_jsonb(x) - 'created_at' - 'updated_at')::text, E'\\n' order by (to_jsonb(x) - 'created_at' - 'updated_at')::text), '') s from public.payments x union all select 'alerts' t, coalesce(string_agg((to_jsonb(x) - 'created_at' - 'updated_at')::text, E'\\n' order by (to_jsonb(x) - 'created_at' - 'updated_at')::text), '') s from public.alerts x union all select 'alert_emails' t, coalesce(string_agg((to_jsonb(x) - 'created_at' - 'updated_at')::text, E'\\n' order by (to_jsonb(x) - 'created_at' - 'updated_at')::text), '') s from public.alert_emails x union all select 'vendors' t, coalesce(string_agg((to_jsonb(x) - 'created_at' - 'updated_at')::text, E'\\n' order by (to_jsonb(x) - 'created_at' - 'updated_at')::text), '') s from public.vendors x union all select 'emails' t, coalesce(string_agg((to_jsonb(x) - 'created_at' - 'updated_at')::text, E'\\n' order by (to_jsonb(x) - 'created_at' - 'updated_at')::text), '') s from public.emails x union all select 'app_state' t, coalesce(string_agg((to_jsonb(x) - 'created_at' - 'updated_at')::text, E'\\n' order by (to_jsonb(x) - 'created_at' - 'updated_at')::text), '') s from public.app_state x"
    p = subprocess.run(["supabase", "db", "query", "--linked", sql], cwd=ROOT, capture_output=True, text=True)
    s = p.stdout
    rows = json.JSONDecoder().raw_decode(s[s.index("{"):])[0]["rows"]
    return {r["t"]: hashlib.sha256((r["s"] or "").encode()).hexdigest() for r in rows}


def sql(q):
    p = subprocess.run(["supabase", "db", "query", "--linked", q], cwd=ROOT, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


JSON_PORT, CLOUD_A, CLOUD_B, LIVE_COPY = 8790, 8788, 8789, 8791
try:
    # ---- 0. dates: 11:30 PM in Houston is still "today" in Houston, whatever the server clock says
    for utc, want in (("2026-11-11T05:30:00+00:00", "2026-11-10"), ("2026-07-11T04:30:00+00:00", "2026-07-10")):
        got = evtime.today_ct(datetime.datetime.fromisoformat(utc)).isoformat()
        check(f"11:30 PM CT ({'CST' if utc[5:7] == '11' else 'CDT'}) -> CT date", got == want, got)
    src = open(os.path.join(ROOT, "server.py")).read()
    naive = src.count("datetime.now(") + src.count("date.today(")
    check("server.py: no machine-clock date calls left", naive == 0, f"{naive} found")

    # ---- 1. start: JSON mode on a scratch copy, two cloud servers (one with a UTC clock, like Vercel)
    work = os.path.join(SCRATCH, "work")
    subprocess.run(["rm", "-rf", work]); subprocess.run(["cp", "-R", SNAP, work], check=True)
    start(JSON_PORT, "json", work)
    start(CLOUD_A, "supabase", work)
    start(CLOUD_B, "supabase", work, tz="UTC")
    before = db_dump()

    # ---- 2. reads identical
    for path in ("/", "/api/data", "/api/brief", "/api/calendar"):
        a, b, c = http(JSON_PORT, path), http(CLOUD_A, path), http(CLOUD_B, path)
        check(f"GET {path}: cloud = JSON files", same(a, b) and same(a, c) and a[0] == 200, f"HTTP {a[0]}/{b[0]}/{c[0]}, {len(a[1])} bytes")

    # ---- 3. writes identical (same TEST actions on both), incl. the alert-folding delete
    fe = "test-4a@example.invalid"  # leak-check: allow: fake .invalid test address
    LEAD, ALERT = "@lead", "@alert"                    # filled in with the ids this run created
    steps = [("/api/add", {"client": "TEST 4a lead", "notes": "TEST"}),
             ("/api/update", {"id": LEAD, "field": "notes", "value": "TEST note 2"}),
             ("/api/update", {"id": LEAD, "field": "event", "value": "2026-12-05"}),
             ("/api/update", {"id": LEAD, "field": "total", "value": "1500"}),
             ("/api/alert-new", {"email_id": "TEST-4a-e1", "from_email": fe, "type": "email", "title": "TEST 4a alert 1",
                                 "detail": "TEST", "at": "2026-11-10T09:00"}),
             ("/api/alert-new", {"email_id": "TEST-4a-e2", "from_email": fe, "type": "inquiry", "title": "TEST 4a new lead",
                                 "detail": "TEST", "at": "2026-11-10T09:05",
                                 "create_lead": {"client": "TEST 4a fold", "src_email": fe, "channel": "Website form"}}),
             ("/api/alert-new", {"email_id": "TEST-4a-e3", "from_email": fe, "type": "email", "title": "TEST 4a merged",
                                 "detail": "TEST merge", "at": "2026-11-10T09:10"}),
             ("/api/alert-meta", {"TEST-4a-e2": False}),
             ("/api/alert", {"id": ALERT, "action": "ignore"}),
             ("/api/alert", {"id": ALERT, "action": "undo"}),
             ("/api/alert", {"id": ALERT, "action": "done"}),
             ("/api/schedule", {"id": LEAD, "action": "add", "label": "TEST deposit", "due": "2026-12-01", "amount": 500, "paid": False}),
             ("/api/schedule", {"id": LEAD, "action": "add", "label": "TEST final", "due": "2027-01-15", "amount": 300}),
             ("/api/schedule", {"id": LEAD, "action": "update", "index": 0, "amount": 650, "paid": False}),
             ("/api/pay", {"id": LEAD, "index": 0}),
             ("/api/schedule", {"id": LEAD, "action": "delete", "index": 1}),
             ("/api/finance", {"field": "collected_2026_manual", "value": 12345}),
             ("/api/brief-ack", {"id": "TEST-brief"})]
    # two real settings get touched: keep their stored text and put it back afterwards
    rc, out = sql("select doc, key, value::text as v from public.app_state where (doc = 'tracker_data' and key in ('finance', 'ignore_senders', '_key_order')) or doc = 'brief_ack'")
    saved_state = json.JSONDecoder().raw_decode(out[out.index("{"):])[0]["rows"]
    made = {"leads": set(), "alerts": set()}
    folded = None
    for port in (JSON_PORT, CLOUD_A):
        last = {}
        outs = []
        for path, body in steps:
            body = dict(body)
            if body.get("id") == LEAD: body["id"] = last["lead"]
            if body.get("id") == ALERT: body["id"] = last["alert"]
            st, raw = http(port, path, body)
            r = json.loads(raw) if st == 200 else {}
            if r.get("lead") and path in ("/api/add", "/api/alert-new"): last.setdefault("lead", r["lead"]["id"])
            if r.get("alert"): last["alert"] = r["alert"]["id"]
            if path == "/api/alert-new" and body["email_id"] == "TEST-4a-e1": first_alert = r["alert"]["id"]
            outs.append((st, raw))
            if port == CLOUD_A:
                if r.get("lead"): made["leads"].add(r["lead"]["id"])
                if r.get("alert"): made["alerts"].add(r["alert"]["id"])
        if port == JSON_PORT: json_outs = outs
        else: cloud_outs, folded = outs, first_alert
    check(f"{len(steps)} TEST saves (every saving route): same answers (cloud = JSON)", all(same(x, y) for x, y in zip(json_outs, cloud_outs)) and all(s == 200 for s, _ in cloud_outs),
          f"{sum(s == 200 for s, _ in cloud_outs)}/{len(steps)} OK")
    a, b = http(JSON_PORT, "/api/data"), http(CLOUD_A, "/api/data")
    check("after writes: /api/data cloud = JSON", same(a, b))
    rc, out = sql(f"select count(*) as n from public.alerts where alert_id = '{folded}'")
    check("fold-alerts path deleted the folded alert in Supabase", '"n": 0' in out)

    # ---- 4. 20 parallel saves across two server processes (Mac + 'Vercel' clock)
    def add(i):
        st, raw = http((CLOUD_A, CLOUD_B)[i % 2], "/api/add", {"client": f"TEST 4a parallel {i:02d}"})
        if st != 200: errors.append(raw.decode("utf-8", "replace")[:160])
        return st, json.loads(raw)["lead"]["id"] if st == 200 else None
    errors = []
    with cf.ThreadPoolExecutor(20) as ex:
        res = list(ex.map(add, range(20)))
    ids = [i for s, i in res if i]
    made["leads"].update(ids)
    check("20 parallel saves: all succeeded", len(ids) == 20, f"{len(ids)}/20 " + " | ".join(errors))
    check("20 parallel saves: 0 duplicate IDs", len(set(ids)) == len(ids))
    rc, out = sql("select count(*) as n from public.leads l join public.clients c using (client_id) where c.name like 'TEST 4a parallel %'")
    check("20 parallel saves: 0 lost (all 20 in Supabase)", '"n": 20' in out, out[out.find('"n"'):][:10])

    # ---- 5. the server's database login is limited

    import db  # noqa: E402
    c = db._connect()
    for name, q in (("read logins (auth.users)", "select 1 from auth.users limit 1"),
                    ("read allowlist (private.app_users)", "select 1 from private.app_users limit 1"),
                    ("read files (storage.objects)", "select 1 from storage.objects limit 1"),
                    ("create a table", "create table public.x_test (i int)"),
                    ("write settings", "insert into public.settings (key, value) values ('x', '1')")):
        try:
            c.run("begin"); c.run(q); c.run("rollback"); check(f"ev_server cannot {name}", False, "allowed")
        except Exception as e:
            c.run("rollback")
            check(f"ev_server cannot {name}", "42501" in str(e) or "permission denied" in str(e), str(e)[:60] if "42501" not in str(e) else "42501")
    c.close()

finally:
    for p in procs:
        p.terminate()
    for p in procs:
        p.wait(10)
    # ---- 6. clean up TEST rows and prove Supabase is exactly as before
    if made["leads"] or made["alerts"]:
        L = ",".join(f"'{x}'" for x in sorted(made["leads"]) if x.startswith("L"))
        A = ",".join(f"'{x}'" for x in sorted(made["alerts"]) if x.startswith("A"))
        ids = f"({L})" if L else "('')"
        aids = f"({A})" if A else "('')"
        rc, out = sql("begin; "
            f"delete from public.alerts where alert_id in {aids} or title like 'TEST 4a%'; "
            f"delete from public.event_days where lead_id in {ids}; delete from public.installments where lead_id in {ids}; "
            f"delete from public.contracts where lead_id in {ids}; "
            f"delete from public.leads l using public.clients c where l.client_id = c.client_id and l.lead_id in {ids} and c.name like 'TEST%'; "
            "delete from public.clients c where c.name like 'TEST 4a%' and not exists (select 1 from public.leads l where l.client_id = c.client_id); "
            "commit;")
        if rc: check("cleanup: TEST rows removed", False, out[-200:])
    for r in (saved_state if "saved_state" in dir() else []):
        sql("update public.app_state set value = cast($ev$" + r["v"] + "$ev$ as json) where doc = '" + r["doc"] + "' and key = '" + r["key"] + "'")
    try:
        check("cleanup: Supabase identical to before the test", db_dump() == before)
    except NameError:
        pass

w = max(len(r[0]) for r in results)
for name, res, got in results:
    print(f"{name:<{w}}  {res}  {got}")
fails = sum(r[1] == "FAIL" for r in results)
print(f"\n{len(results) - fails} pass, {fails} fail")
sys.exit(1 if fails else 0)
