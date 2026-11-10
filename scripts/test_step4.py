#!/usr/bin/env python3
"""Step 4 pass/fail: contracts online. Uses a TEST lead only; never writes to ~/Documents (the
Finder copy job writes to a scratch folder); no email is sent (cloud mode only queues it). Saves go
through test servers on :8789 (working renderer) and :8791 (broken renderer). Supabase, the files
table and the file registry are restored afterwards and checked. Prints counts and PASS/FAIL only.

  .venv/bin/python scripts/test_step4.py <scratch dir with snap/>     exit 0 = all pass
"""
import base64, hashlib, json, os, re, socket, subprocess, sys, time, urllib.parse, urllib.request, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["EV_BACKEND"] = "supabase"
import db, docstore, evenv  # noqa: E402

SCRATCH = sys.argv[1]
SNAP = os.path.join(SCRATCH, "snap")
PY = sys.executable
RENDER_PY = os.path.expanduser(os.environ.get("EV_PYTHON", "~/.hermes/venvs/ev/bin/python"))
results, procs = [], []
FIELDS = {k: f"TEST {k}" for k in ("addons", "client_address", "client_email", "client_phone", "coverage_hours", "day_of_contact",
                                     "image_estimate", "inclusions", "locations", "package_name", "photographers", "privacy_option",
                                     "session_type", "travel_fee")}
FIELDS.update({"client_names": "TEST Client", "first_names": "TEST", "city_state": "Houston, TX", "start_time": "4:00 PM", "end_time": "10:00 PM"})  # leak-check: allow: the business's home city as a generic TEST placeholder


T0 = time.time()


def check(name, ok, got=""):
    results.append((name, "PASS" if ok else "FAIL", f"{got} [{time.time() - T0:.0f}s]".strip()))


def start(port, extra):
    env = dict(os.environ, EV_BACKEND="supabase", EV_PORT=str(port), EV_DATA_DIR=SNAP, EV_DOCS_DIR=os.path.join(SCRATCH, "docs"), **extra)
    procs.append(subprocess.Popen([PY, os.path.join(ROOT, "server.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE))
    for _ in range(100):
        try: socket.create_connection(("127.0.0.1", port), 0.2).close(); return
        except OSError: time.sleep(0.1)
    raise SystemExit(f"server on {port} did not start")


def http(port, path, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def q(sql, **kw):
    return db._read_only(lambda c: c.run(sql, **kw))


def w(sql, **kw):
    c = db._connect()
    try:
        c.run("begin"); c.run(sql, **kw); c.run("commit")
    finally:
        c.close()


def docx_text(data):
    import io
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return re.sub(r"<[^>]+>", "", z.read("word/document.xml").decode("utf-8"))


def pdf_pages(data):
    return len(re.findall(rb"/Type\s*/Page(?!s)", data))


def counts():
    return {"files": q("select count(*) from public.files")[0][0], "registry": len(db.file_registry()),
            "outbox": q("select count(*) from public.outbox")[0][0], "contracts": q("select count(*) from public.contracts")[0][0]}


reg_before = db.file_registry()
keys_before = {k for (k,) in q("select file_key from public.files")}
lead = None
try:
    start(8789, {"EV_PYTHON": RENDER_PY})
    start(8791, {"EV_PYTHON": "/usr/bin/false"})
    check("setup: 23 registered files + wording in the database", len(keys_before) == 24 and docstore.CONTENT_KEY in keys_before, f"{len(keys_before)} files")

    # ---- A. VFinal links served from the database
    served = os.path.expanduser(evenv.need("EV_SERVED_DIR"))
    same = 0
    for name, local in (("EMANANT VISUALS - CONTRACT - VFinal.pdf", "contract.pdf"), ("EMANANT VISUALS - CONTRACT - VFinal.docx", "contract.docx"),
                        ("EMANANT VISUALS - Client To-Do Questionnaire - VFinal.pdf", "questionnaire.pdf"),
                        ("EMANANT VISUALS - Client To-Do Questionnaire - VFinal.docx", "questionnaire.docx")):
        st, b = http(8789, "/docs/" + urllib.parse.quote(name))
        same += st == 200 and b == open(os.path.join(served, local), "rb").read()
    check("A. VFinal template links served from the database, byte-identical", same == 4, f"{same}/4")

    # ---- B. create a contract on a TEST lead
    st, b = http(8789, "/api/add", {"client": "TEST 4 contract lead"})
    lead = json.loads(b)["lead"]["id"]
    body = {"id": lead, "fields": FIELDS, "total": 3000, "retainer": 1000,
            "days": [{"date": "2027-03-14", "event": "TEST Walima", "start": "4:00 PM", "end": "10:00 PM", "hours": "6"}],
            "plan": [{"label": "TEST second payment", "due": "2027-01-15", "amount": 1000}]}
    c0 = counts()
    st, b = http(8789, "/api/contract/create", body)
    r = json.loads(b) if st == 200 else {}
    c1 = counts()
    terms = (r.get("lead") or {}).get("contract_terms") or {}
    drafts = terms.get("draft_files") or []
    check("B. contract created", st == 200 and len(drafts) == 2 and all(d.startswith(docstore.DOCS_TILDE + "/Contract Drafts/") for d in drafts),
          f"HTTP {st}" + ("" if st == 200 else " " + b.decode()[:120]))
    reg = {m["source"]: m for m in db.file_registry()}
    rows = {k: (h, bytes(d)) for k, h, d in q("select file_key, sha256, data from public.files where file_key like 'drafts/%TEST%'")}
    check("B. both files + registry saved with the contract", c1["files"] == c0["files"] + 2 and c1["registry"] == c0["registry"] + 2
          and all(reg.get(d) and rows.get(reg[d]["key"], ("",))[0] == reg[d]["sha256"] for d in drafts))
    docs = q("select d.kind, d.storage_key from public.documents d join public.contracts k using (contract_id) where k.lead_id = :l", l=lead)
    check("B. documents linked to the contract", sorted(k for k, _ in docs) == ["draft", "draft"] and all(s in rows for _, s in docs))
    ob = q("select o.to_addr, count(f.*), array_agg(f.sha256) from public.outbox o left join public.outbox_files f using (outbox_id) group by o.outbox_id order by o.outbox_id desc limit 1")
    check("B. review email queued to Eman with both files attached", c1["outbox"] == c0["outbox"] + 1 and ob and ob[0][0] in ("self", evenv.need("EV_FROM_EMAIL")) and ob[0][1] == 2
          and sorted(ob[0][2]) == sorted(h for h, _ in rows.values()))
    # same document as the Mac's renderer makes from the same terms
    tmp = os.path.join(SCRATCH, "local-render")
    code = ("import sys,json,os; sys.path.insert(0,%r); os.environ['EV_BACKEND']='json'; import server; "
            "t=json.load(open(%r)); print(json.dumps(server.render('contract', server.build_fill(t), %r)))") % (ROOT, os.path.join(SCRATCH, "terms.json"), os.path.join(tmp, "x"))
    json.dump(terms, open(os.path.join(SCRATCH, "terms.json"), "w"))
    p = subprocess.run([PY, "-c", code], capture_output=True, text=True, env=dict(os.environ, EV_BACKEND="json"), cwd=ROOT)
    local = json.loads(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 else []
    cloud = {os.path.splitext(k)[1]: d for k, (h, d) in rows.items()}
    lpdf = open([x for x in local if x.endswith(".pdf")][0], "rb").read() if local else b""
    ldocx = open([x for x in local if x.endswith(".docx")][0], "rb").read() if local else b""
    check("B. same document as the Mac renderer (Word text identical, same PDF page count)",
          bool(local) and docx_text(cloud[".docx"]) == docx_text(ldocx) and pdf_pages(cloud[".pdf"]) == pdf_pages(lpdf) > 0,
          f"{pdf_pages(cloud.get('.pdf', b''))} PDF pages" if local else p.stderr[-160:])

    # ---- C. renderer broken -> nothing saved at all
    st2, b2 = http(8791, "/api/add", {"client": "TEST 4 broken lead"})
    lead2 = json.loads(b2)["lead"]["id"]
    c2 = counts()
    st, b = http(8791, "/api/contract/create", dict(body, id=lead2))
    c3 = counts()
    has = q("select count(*) from public.contracts where lead_id = :l", l=lead2)[0][0]
    check("C. renderer fails -> error, and no files/registry/email/contract saved", st == 500 and c3 == c2 and has == 0, f"HTTP {st}")

    # ---- D. contract signed (DocuSeal path): signed copy + questionnaire, queued to Eman
    pdf = b"%PDF-1.4\n% TEST signed contract\n" + b"0" * 2000
    c4 = counts()
    st, b = http(8789, "/api/contract-signed", {"lead_id": lead, "pdf_b64": base64.b64encode(pdf).decode()})
    r = json.loads(b) if st == 200 else {}
    t2 = (r.get("lead") or {}).get("contract_terms") or {}
    c5 = counts()
    signed_ok = t2.get("signed_file", "").startswith(docstore.DOCS_TILDE + "/Signed Contracts/")
    sig = {m["source"]: m for m in db.file_registry()}.get(t2.get("signed_file"))
    check("D. signed: lead signed, signed PDF saved byte-identical", st == 200 and r["lead"]["contract"] == "signed" and signed_ok and sig
          and sig["sha256"] == hashlib.sha256(pdf).hexdigest(), f"HTTP {st}")
    check("D. questionnaire made, saved and queued to Eman", len(t2.get("questionnaire_files") or []) == 2 and c5["files"] == c4["files"] + 3
          and c5["outbox"] == c4["outbox"] + 1 and "Questionnaire emailed to Eman." in (r.get("notes") or []))

    # ---- E. Finder copy job (scratch folder instead of ~/Documents)
    sync = os.path.join(SCRATCH, "sync")
    subprocess.run(["rm", "-rf", sync])                    # start from an empty folder
    conflict = os.path.join(sync, "Contract Drafts", os.path.basename(drafts[0]))
    os.makedirs(os.path.dirname(conflict), exist_ok=True)
    open(conflict, "wb").write(b"a different file with the same name")
    env = dict(os.environ, EV_BACKEND="supabase", EV_SYNC_ROOT=sync)
    o1 = subprocess.run([PY, os.path.join(ROOT, "docs_sync.py")], env=env, capture_output=True, text=True).stdout.strip()
    o2 = subprocess.run([PY, os.path.join(ROOT, "docs_sync.py")], env=env, capture_output=True, text=True).stdout.strip()
    stem, ext = os.path.splitext(conflict)
    ok_files = all(hashlib.sha256(open(os.path.join(sync, m["source"][len(docstore.DOCS_TILDE) + 1:]), "rb").read()).hexdigest() == m["sha256"]
                   for m in db.file_registry() if m["source"].startswith(docstore.DOCS_TILDE + "/") and m["source"] != drafts[0])
    check("E. Finder copy: every file written and checked", ok_files and " 0 errors" in o1, o1)
    check("E. never overwrites: existing different file kept, cloud version saved beside it",
          open(conflict, "rb").read() == b"a different file with the same name" and os.path.exists(f"{stem} (cloud copy){ext}"))
    check("E. second run adds nothing", o2.startswith("docs sync: 0 added, 0 saved as cloud copy"), o2)
finally:
    for p in procs:
        p.terminate()
    for p in procs:
        p.wait(10)
    try:
        extra = [k for (k,) in q("select file_key from public.files") if k not in keys_before]
        w("delete from public.files where file_key = any(cast(:k as text[]))", k=extra)
        w("update public.app_state set value = cast(:v as json) where doc = 'storage_manifest' and key = 'files'", v=json.dumps(reg_before, ensure_ascii=False))
        w("delete from public.outbox")
    except Exception as ex:
        print("cleanup failed:", ex)
    env = dict(os.environ, EV_DATA_DIR=SNAP)
    r1 = subprocess.run([PY, os.path.join(ROOT, "scripts", "migrate_v2.py")], env=env, capture_output=True, text=True)
    r2 = subprocess.run([PY, os.path.join(ROOT, "scripts", "verify_v2.py")], env=env, capture_output=True, text=True)
    same_files = {k for (k,) in q("select file_key from public.files")} == keys_before and db.file_registry() == reg_before
    check("cleanup: files + registry as before; data reloaded and verified exact", r1.returncode == 0 and r2.returncode == 0 and same_files,
          (r2.stdout.strip().splitlines()[-1] if r2.stdout.strip() else "") + ("" if r1.returncode == 0 else " | reload failed: " + r1.stderr.strip()[-200:]))

width = max(len(r[0]) for r in results)
for name, res, got in results:
    print(f"{name:<{width}}  {res}  {got}")
fails = sum(r[1] == "FAIL" for r in results)
print(f"\n{len(results) - fails} pass, {fails} fail")
sys.exit(1 if fails else 0)
