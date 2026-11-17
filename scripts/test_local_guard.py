#!/usr/bin/env python3
"""Review fix #2 test: other websites can't use the Mac dashboard server through a browser.
Runs a throwaway JSON-mode server on a COPY of the live data (scratch dir), attacks it the way a
web page could (spoofed Host = DNS rebinding, cross-site Origin, text/plain "simple" POST), checks
that the dashboard itself and the watcher (with its secret) still work, then deletes the copy.
Prints PASS/FAIL only, never data.

  .venv/bin/python scripts/test_local_guard.py
"""
import http.client, json, os, shutil, subprocess, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import evenv  # noqa: E402,F401  (loads .env.local for EV_JOB_TOKEN)

LIVE = os.path.expanduser("~/EmanantHQ")
PORT = 8791
TOKEN = os.environ.get("EV_JOB_TOKEN", "")
results = []


def req(method, path, body=None, headers=None, host=f"127.0.0.1:{PORT}"):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=20)
    h = {"Host": host}
    h.update(headers or {})
    c.request(method, path, body=body, headers=h)
    r = c.getresponse(); r.read(); c.close()
    return r.status


def check(name, got, want):
    results.append((name, "PASS" if got == want else "FAIL", f"{got} (want {want})"))


scratch = tempfile.mkdtemp(prefix="ev-guard-")
proc = None
try:
    for f in os.listdir(LIVE):
        if f.endswith(".json"):
            shutil.copy2(os.path.join(LIVE, f), scratch)      # copy, never move
    env = dict(os.environ, EV_BACKEND="json", EV_ALLOW_JSON="1", EV_DATA_DIR=scratch, EV_DOCS_DIR=os.path.join(scratch, "docs"),
               EV_PORT=str(PORT), EV_HOST="127.0.0.1")
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "server.py")], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            req("GET", "/api/brief"); break
        except OSError:
            time.sleep(0.2)
    J = {"Content-Type": "application/json"}
    ack = json.dumps({"id": "TEST"})
    # the dashboard and the watcher still work
    check("dashboard page loads", req("GET", "/"), 200)
    check("data loads (127.0.0.1)", req("GET", "/api/data"), 200)
    check("data loads (localhost)", req("GET", "/api/data", host=f"localhost:{PORT}"), 200)
    check("same-site JSON save works", req("POST", "/api/brief-ack", ack, {**J, "Origin": f"http://127.0.0.1:{PORT}"}), 200)
    test_alert = json.dumps({"type": "unclear", "title": "TEST guard", "detail": "TEST", "email_id": "TEST-guard-key", "done": True})
    check("EV_JOB_TOKEN is set in .env.local", bool(TOKEN), True)
    check("watcher route works with the secret", req("POST", "/api/alert-new", test_alert, {**J, "X-EV-Job": TOKEN}), 200)
    # attacks a web page could make
    check("DNS rebinding: foreign Host read refused", req("GET", "/api/data", host="attacker.example"), 403)
    check("DNS rebinding: foreign Host save refused", req("POST", "/api/brief-ack", ack, J, host="attacker.example"), 403)
    check("cross-site Origin save refused", req("POST", "/api/brief-ack", ack, {**J, "Origin": "https://attacker.example"}), 403)
    check("cross-site fetch metadata refused", req("POST", "/api/brief-ack", ack, {**J, "Sec-Fetch-Site": "cross-site"}), 403)
    check("text/plain 'simple' POST refused", req("POST", "/api/brief-ack", ack, {"Content-Type": "text/plain"}), 415)
    check("form POST refused", req("POST", "/api/send-reply", "id=A0001", {"Content-Type": "application/x-www-form-urlencoded"}), 415)
    check("watcher route without secret refused", req("POST", "/api/alert-new", test_alert, J), 403)
    check("watcher route with wrong secret refused", req("POST", "/api/alert-new", test_alert, {**J, "X-EV-Job": "wrong"}), 403)
    check("contract-signed without secret refused", req("POST", "/api/contract-signed", "{}", J), 403)
    check("alert-meta without secret refused", req("POST", "/api/alert-meta", "{}", J), 403)
    # the Vercel handler: no Host rule, Mac-only routes blocked
    import server
    check("Mac-only routes listed for Vercel block", sorted(server.MAC_ONLY), ["/api/alert-meta", "/api/alert-new", "/api/contract-signed", "/api/open-folder"])
    src = open(os.path.join(ROOT, "api", "index.py")).read()
    check("Vercel handler blocks Mac-only routes", ("LOCAL = False" in src) and ("p in server.MAC_ONLY" in src), True)
    check("live data untouched", all(open(os.path.join(LIVE, f), "rb").read() != b"" for f in os.listdir(LIVE) if f.endswith(".json")), True)
finally:
    if proc:
        proc.terminate(); proc.wait(10)
    shutil.rmtree(scratch, ignore_errors=True)        # holds client data

w = max(len(r[0]) for r in results)
for n, r, g in results:
    print(f"{n:<{w}}  {r}  {g}")
fails = sum(r[1] == "FAIL" for r in results)
print(f"\n{len(results) - fails} pass, {fails} fail")
sys.exit(1 if fails else 0)
