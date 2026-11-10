#!/usr/bin/env python3
"""Phase 2 pass/fail test against the REAL Supabase project, from outside (the way an attacker would).
Uses only the public anon key. Never prints a key, password or row content. Writes nothing that
could succeed: every write attempt is expected to be refused.

Needs in .env.local (gitignored):
  SUPABASE_URL, SUPABASE_ANON_KEY
  EV_TEST_STRANGER_EMAIL / EV_TEST_STRANGER_PASSWORD  - a test user Ibrahim created in the dashboard,
                                                        NOT on the allowlist
  EV_TEST_ALLOWED_EMAIL / EV_TEST_ALLOWED_PASSWORD    - optional: an allowlisted user (positive check)
  EV_TEST_STORAGE_OBJECT                              - optional: path of a dummy file in bucket
                                                        'contracts', e.g. test/probe.pdf
Run:  python3 scripts/test_rls_live.py      exit 0 = all pass
"""
import json, os, sys, urllib.error, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import evenv  # noqa: E402,F401  (loads .env.local)

URL = evenv.need("SUPABASE_URL").rstrip("/")
ANON = evenv.need("SUPABASE_ANON_KEY")
TABLES = ["leads", "alerts", "vendors", "payments", "changelog", "seen_emails", "app_state", "settings"]
results = []


def call(method, path, token=None, body=None, extra_headers=None):
    h = {"apikey": ANON, "Authorization": f"Bearer {token or ANON}", "Content-Type": "application/json",
         "Prefer": "return=representation"}
    h.update(extra_headers or {})
    req = urllib.request.Request(URL + path, method=method, headers=h, data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def rows(status, raw):
    try: return len(json.loads(raw)) if status == 200 else None
    except Exception: return None


def check(name, ok, got):
    results.append((name, "PASS" if ok else "FAIL", got))


def login(email_var, pw_var):
    e, p = os.environ.get(email_var), os.environ.get(pw_var)
    if not (e and p): return None
    s, raw = call("POST", "/auth/v1/token?grant_type=password", body={"email": e, "password": p})
    if s != 200: check(f"login {email_var}", False, f"HTTP {s}"); return None
    return json.loads(raw)["access_token"]


def reads(who, token, expect_rows):
    for t in TABLES:
        s, raw = call("GET", f"/rest/v1/{t}?select=*&limit=5", token)
        n = rows(s, raw)
        ok = (n is not None and n > 0) if expect_rows else (n == 0 or s in (401, 403, 404))
        check(f"{who} read {t}", ok, f"HTTP {s}, {n if n is not None else '-'} rows")


FILTER = {"app_state": "key=neq.__none__", "settings": "key=neq.__none__", "changelog": "seq=gte.0"}  # PostgREST needs a filter
PATCH = {"changelog": {"field": "x"}, "seen_emails": {"pos": 0}}


def writes(who, token):
    for t in TABLES:
        f = FILTER.get(t, "pos=gte.0")
        s, _ = call("POST", f"/rest/v1/{t}", token, body={})
        check(f"{who} insert {t}", s in (401, 403), f"HTTP {s}")
        s, raw = call("PATCH", f"/rest/v1/{t}?{f}", token, body=PATCH.get(t, {"updated_at": "2000-01-01T00:00:00Z"}))
        check(f"{who} update {t}", s in (401, 403) or rows(s, raw) == 0, f"HTTP {s}, {rows(s, raw)} rows")
        s, raw = call("DELETE", f"/rest/v1/{t}?{f}", token)
        check(f"{who} delete {t}", s in (401, 403) or rows(s, raw) == 0, f"HTTP {s}, {rows(s, raw)} rows")
    s, _ = call("POST", "/rest/v1/rpc/is_allowed", token, body={})
    check(f"{who} call private function", s in (401, 403, 404), f"HTTP {s}")


def storage(who, token, expect_ok):
    obj = os.environ.get("EV_TEST_STORAGE_OBJECT", "test/probe.pdf")
    s, _ = call("GET", f"/storage/v1/object/authenticated/contracts/{obj}", token)
    check(f"{who} Storage download", (s == 200) if expect_ok else s != 200, f"HTTP {s}")
    s, _ = call("GET", f"/storage/v1/object/public/contracts/{obj}", None)
    check(f"{who} Storage public URL", s != 200, f"HTTP {s}")
    s, _ = call("POST", "/storage/v1/object/contracts/test/should-fail.pdf", token, body={},
                extra_headers={"Content-Type": "application/pdf"})
    check(f"{who} Storage upload", s != 200, f"HTTP {s}")
    s, raw = call("POST", "/storage/v1/object/list/contracts", token, body={"prefix": "", "limit": 5})
    n = rows(s, raw)
    check(f"{who} Storage list", (n or 0) > 0 if expect_ok else (n in (0, None)), f"HTTP {s}, {n if n is not None else '-'} items")


# 1) anon
reads("anon", None, False); writes("anon", None); storage("anon", None, False)
s, _ = call("POST", "/auth/v1/signup", body={"email": "nobody@example.invalid", "password": "x" * 16})  # leak-check: allow: fake probe address, .invalid TLD never delivers
check("anon sign-up refused", s in (400, 403, 422), f"HTTP {s}")
# 2) signed in, not on the allowlist
tok = login("EV_TEST_STRANGER_EMAIL", "EV_TEST_STRANGER_PASSWORD")
if tok: reads("stranger", tok, False); writes("stranger", tok); storage("stranger", tok, False)
else: check("stranger tests", False, "EV_TEST_STRANGER_* not set")
# 3) allowlisted (optional positive check — proves the tests above aren't passing for the wrong reason)
tok = login("EV_TEST_ALLOWED_EMAIL", "EV_TEST_ALLOWED_PASSWORD")
if tok:
    writes("allowed", tok)
    s, raw = call("GET", "/rest/v1/leads?select=id&limit=1", tok)
    check("allowed read leads (HTTP 200)", s == 200, f"HTTP {s}")
    if os.environ.get("EV_TEST_STORAGE_OBJECT"): storage("allowed", tok, True)

w = max(len(r[0]) for r in results)
for name, res, got in results: print(f"{name:<{w}}  {res}  {got}")
fails = sum(r[1] == "FAIL" for r in results)
print(f"\n{len(results) - fails} pass, {fails} fail")
sys.exit(1 if fails else 0)
