#!/usr/bin/env python3
"""Step 4: put every registered contract file + the private contract wording into the `files`
table, so the cloud can serve and use them. Copies only (never moves); each file must match the
SHA-256 in the registry, else nothing is written. Re-runnable. Prints counts only.

  .venv/bin/python scripts/load_files.py
"""
import hashlib, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["EV_BACKEND"] = "supabase"
import db, docstore, evenv  # noqa: E402

reg = db.file_registry()
todo = []
for m in reg:
    p = os.path.expanduser(m["source"])
    with open(p, "rb") as fh:
        data = fh.read()
    if hashlib.sha256(data).hexdigest() != m["sha256"]:
        sys.exit(f"refusing: a file changed since it was registered ({m['key']})")
    todo.append((m["key"], m.get("type") or docstore.ctype(p), data))
cpath = os.path.join(os.path.expanduser(evenv.need("EV_CONTRACT_CONTENT_DIR")), "contract_final_content.py")
with open(cpath, "rb") as fh:
    content = fh.read()

c = db._connect()
try:
    c.run("begin")
    for key, ctype, data in todo + [(docstore.CONTENT_KEY, "text/x-python", content)]:
        c.run("insert into public.files (file_key, content_type, data, sha256, bytes) values (:k, :t, :d, :h, :n) "
              "on conflict (file_key) do update set content_type = excluded.content_type, data = excluded.data, "
              "sha256 = excluded.sha256, bytes = excluded.bytes",
              k=key, t=ctype, d=data, h=hashlib.sha256(data).hexdigest(), n=len(data))
    c.run("commit")
finally:
    c.close()
got = db._read_only(lambda c: c.run("select file_key, sha256 from public.files"))
have = {k: h for k, h in got}
ok = sum(have.get(m["key"]) == m["sha256"] for m in reg)
print(f"registered files in the database with matching SHA-256: {ok} / {len(reg)}; contract wording loaded: {docstore.CONTENT_KEY in have}")
sys.exit(0 if ok == len(reg) and docstore.CONTENT_KEY in have else 1)
