#!/usr/bin/env python3
"""Review fix #1 test: after a rollback, the OLD scripts must not re-import or re-alert anything.
Exports Supabase into a scratch folder (scripts/export_json.py, read-only on Supabase), then replays
the OLD importer's and OLD watcher's dedupe rules (from ~/EmanantHQ, read-only) against the mailbox
as it is right now (read-only himalaya). Nothing is imported, posted or written outside scratch.
Prints counts and PASS/FAIL only; deletes the scratch folder (it holds client data).

  .venv/bin/python scripts/test_rollback_keys.py
"""
import json, os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["EV_BACKEND"] = "supabase"
import evenv  # noqa: E402

results = []


def hj(*args):
    r = subprocess.run(["himalaya", "--json", *args], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise SystemExit("mailbox not readable: " + r.stderr[-200:])
    j = json.loads(r.stdout)
    return j["envelopes"] if isinstance(j, dict) else j


scratch = tempfile.mkdtemp(prefix="ev-rollback-")
try:
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "export_json.py"), scratch], capture_output=True, text=True, timeout=600)
    results.append(("export ran", "PASS" if r.returncode == 0 else "FAIL", r.stdout.strip().split("payments")[-1][:90] if r.returncode == 0 else r.stderr[-200:]))
    pays = json.load(open(os.path.join(scratch, "payments.json")))
    ws = json.load(open(os.path.join(scratch, "watch_state.json")))
    # 1. OLD zelle_import: `if e["id"] in {p["email_id"]}: continue` -> anything else is imported again
    sender = evenv.need("EV_ZELLE_SENDER")
    zelle = hj("envelope", "search", "-s", "500", f'from {sender} and subject "You received money with Zelle" order by date desc')
    have = {str(p["email_id"]) for p in pays}
    again = [e for e in zelle if e["id"] not in have]
    results.append(("old Zelle importer would re-import", "PASS" if not again else "FAIL", f"{len(again)} of {len(zelle)} Zelle emails"))
    results.append(("every payment key is a mailbox number or a gone email", "PASS" if all(str(p['email_id']).isdigit() or '@' in str(p['email_id']) for p in pays) else "FAIL", f"{len(pays)} payments"))
    # 2. OLD watcher: key = message-id or bare mailbox number; `if key in seen: continue`
    since = __import__("datetime").date.today() - __import__("datetime").timedelta(days=3)
    envs = hj("envelope", "search", "-s", "300", f"after {since.isoformat()} order by date asc")
    seen = set(ws["seen"])
    unseen = [e for e in envs if (e.get("message-id") or e["id"]) not in seen]
    results.append(("old watcher would re-alert (inbox, last 3 days)", "PASS" if not unseen else "FAIL",
                    f"{len(unseen)} of {len(envs)} (only mail newer than the last cloud run may appear)"))
    results.append(("no 'inbox:'/'junk:' keys left for the old watcher", "PASS" if not any(k.startswith(("inbox:", "junk:")) for k in seen) else "FAIL", f"{len(seen)} seen keys"))
finally:
    shutil.rmtree(scratch, ignore_errors=True)

w = max(len(x[0]) for x in results)
for n, res, got in results:
    print(f"{n:<{w}}  {res}  {got}")
fails = sum(x[1] == "FAIL" for x in results)
print(f"\n{len(results) - fails} pass, {fails} fail")
sys.exit(1 if fails else 0)
