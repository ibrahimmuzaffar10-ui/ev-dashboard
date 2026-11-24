"""Contract + payment-matching checks (pure functions and one local render; no database writes, no email).

    EV_BACKEND=supabase .venv/bin/python scripts/test_contracts.py     (expect: 30/30 ALL PASS; reads nothing live)

Uses made-up people only. The render check needs the contract wording (EV_CONTRACT_CONTENT_DIR) and the
renderer Python (EV_PYTHON); it is skipped where those are missing.
"""
import datetime, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "scripts"))
import server, zelle_import as z, send_contract as sc  # noqa: E402

results = []
def check(name, ok):
    results.append((name, bool(ok))); print(("PASS " if ok else "FAIL ") + name)

D = datetime.date
# sign-by: 7 days, or the day before the event if sooner, never before today
t0 = D(2026, 11, 23)
for ev, exp in ((None, "2026-11-30"), ("2026-11-28", "2026-11-27"), ("2026-12-19", "2026-11-30"),
                ("2026-11-24", "2026-11-23"), ("2026-11-23", "2026-11-23"), ("2026-12-01", "2026-11-30")):
    check(f"sign_by event={ev}", server.sign_by_date(t0, [ev] if ev else []) == exp)

terms = {"fields": {"client_names": "Test Person", "first_names": "Test", "privacy_option": "Full Privacy (+$N)".replace("N", "1"),
                    "session_type": "Engagement Shoot", "client_email": "test" + "@" + "example.com"},
         "days": [{"event": "Shoot", "date": "2026-12-05", "start": "4 PM", "end": "6 PM", "hours": "2"}],
         "plan": [{"label": "Final balance", "due": "2026-12-05", "amount": 40}], "issue": "2026-11-23", "sign_by": "2026-11-30",
         "total": 50, "retainer": 10}
plan = server.plan_from_terms(terms, "2026-11-30")
check("plan: deposit + installments, all unpaid", [(x["amount"], x["paid"]) for x in plan] == [(10, False), (40, False)])
check("plan: deposit due by sign-by", plan[0]["due"] == "2026-11-30")
check("plan total = contract total", sum(x["amount"] for x in plan) == terms["total"])

os.environ["EV_REP_NAME"] = "Rep Name"
f = server.build_fill(terms)
check("privacy line has no fee", f["privacy_option"] == "Full Privacy")
check("rep pre-signs", f["rep_name"] == "Rep Name" and f["rep_presign"] is True)
check("offer days = 7", f["offer_days"] == 7)
t2 = dict(terms, fields=dict(terms["fields"], privacy_option=""))
check("no privacy tier = Standard usage", server.build_fill(t2)["privacy_option"] == "Standard usage")

# client email
to, subj, body = sc.contract_email(terms, "https://docuseal.com/s/TEST", 2026)
check("email: Hi + first name", body.startswith("Hi Test,"))
check("email: event lower case, date", "your engagement shoot on Sat Dec 5 is ready" in body)
check("email: sign-by in subject + body", "sign by Nov 30" in subj and "Please sign by Nov 30" in body)
check("email: deposit amount", "the " + "$" + "10 deposit" in body)
t3 = dict(terms, fields=dict(terms["fields"], first_names="Dr. Test"))
check("email: title skipped", sc.contract_email(t3, "x", 2026)[2].startswith("Hi Test,"))

# Zelle matching: one person's name at a time; never above the booking total
lead = {"id": "L900", "client": "Kiwi Lime & Mango Y (planner Plum)", "total": 300, "contract_terms": {"fields": {"client_names": "Kiwi Lime"}}}
toks = lambda s: set(re.findall(r"[a-z]{3,}", (s or "").lower())) - {"and", "the", "via", "muhammad", "mohammad", "ali"}  # leak-check: allow: very common names excluded from fuzzy matching (same list as zelle_import.py), not a person
hit = lambda payer: any(len(toks(payer) & toks(seg)) >= min(2, len(toks(payer))) for seg in z.name_segments(lead))
check("match: Kiwi Lime", hit("KIWI LIME"))
check("match: one-name payer MANGO matches its person", hit("MANGO"))
check("no match: Mango Lime (two people mixed)", not hit("MANGO LIME"))
pays = [{"lead_id": "L900", "amount": 200}]
check("over total: 200 + 100 = 300 ok", not z.over_total(lead, {"amount": 100}, pays))
check("over total: 200 + 150 > 300 held", z.over_total(lead, {"amount": 150}, pays))
check("over total: counts this run's matches", z.over_total(lead, {"amount": 100}, pays, extra=50))

# one local render: one box ticked, deliverables, short-notice wording, signature row
if os.environ.get("EV_CONTRACT_CONTENT_DIR") and os.path.exists(server.VENV_PY):
    t4 = dict(terms, sign_by="2026-11-27", fields=dict(terms["fields"], image_estimate="99+ fully edited images · 1 roll of film"))
    out = os.path.join(tempfile.mkdtemp(), "t")
    try:
        server.render("contract", server.build_fill(t4), out)
        txt = subprocess.run([server.VENV_PY, "-c", "import pypdfium2,sys;d=pypdfium2.PdfDocument(sys.argv[1]);print(len(d));print(''.join(d[i].get_textpage().get_text_range() for i in range(len(d))))", out + ".pdf"],
                             capture_output=True, text=True).stdout
        flat = re.sub(r"\s+", " ", txt)
        check("render: exactly one privacy box ticked", flat.count("[X]") == 1 and "[X] Full Privacy" in flat)
        check("render: deliverables written out", "Estimated deliverables: 99+ fully edited images · 1 roll of film" in flat and "edited images+ edited" not in flat)
        check("render: short-notice wording (4 days)", "valid from the date it is sent until the sign-by date" in flat and "seven (7) days from the date" not in flat)
        check("render: rep row signed + dated", "Rep Name" in flat and "Nov 23, 2026" in flat)
        check("render: 8 pages (DocuSeal field positions)", txt.split("\n", 1)[0].strip() == "8")
    finally:
        for ext in (".pdf", ".docx"):
            if os.path.exists(out + ext): os.remove(out + ext)
    bad = dict(terms, fields=dict(terms["fields"], privacy_option="Platinum Privacy"))
    try:
        server.render("contract", server.build_fill(bad), os.path.join(tempfile.mkdtemp(), "bad")); check("render: unknown privacy choice refused", False)
    except RuntimeError:
        check("render: unknown privacy choice refused", True)
else:
    print("SKIP render checks (no contract wording / renderer here)")

n = sum(ok for _, ok in results)
print(f"\n{n}/{len(results)} passed" + ("  ALL PASS" if n == len(results) else ""))
sys.exit(0 if n == len(results) else 1)
