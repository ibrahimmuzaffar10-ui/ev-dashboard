#!/usr/bin/env python3
"""Phase 3: contract files -> private Storage bucket `contracts`, verified by SHA-256.

Copies (never moves) every file from the folders below, uploads it with an explicit content type,
downloads it back and compares SHA-256, then writes a manifest (original path -> Storage key,
sha256, bytes) to app_state ('storage_manifest', 'files'). Prints counts only.
File paths inside lead records are NOT rewritten (raw stays exact); the manifest maps them.

  python3 scripts/migrate_files.py <scratch dir>      exit 0 = every file verified
The scratch dir gets copies of client files: delete it afterwards.
"""
import hashlib, json, os, re, secrets, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import evenv  # noqa: E402  (loads .env.local)

DOCS = os.path.expanduser(evenv.need("EV_DOCS_DIR"))
DATA = os.path.expanduser(evenv.need("EV_DATA_DIR"))
SOURCES = {                                   # Storage prefix -> local folder
    "drafts": os.path.join(DOCS, "Contract Drafts"),
    "signed": os.path.join(DOCS, "Signed Contracts"),
    "questionnaires": os.path.join(DOCS, "Questionnaires"),
    "templates/documents": os.path.join(DOCS, "Contracts"),
    "templates/served": os.path.expanduser(evenv.need("EV_SERVED_DIR")),
    "pending": os.path.join(DATA, "contracts", "pending"),
}
TYPES = {".pdf": "application/pdf", ".json": "application/json",
         ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
HOME = os.path.expanduser("~")


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def clean(name):                                # Storage keys: ASCII only
    name = name.replace("–", "-").replace("—", "-")
    return re.sub(r"[^A-Za-z0-9 _.()'!,&+=@-]", "_", name)


def sb(*args):
    p = subprocess.run(["supabase", *args], capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(f"supabase {args[0]} {args[1]} failed: {p.stderr.strip()[-300:]}")
    return p.stdout


def main(scratch):
    up, down = os.path.join(scratch, "up"), os.path.join(scratch, "down")
    os.makedirs(up, exist_ok=True); os.makedirs(down, exist_ok=True)
    plan, keys = [], set()
    for prefix, folder in SOURCES.items():
        if not os.path.isdir(folder):
            sys.exit(f"missing folder for {prefix}")
        for name in sorted(os.listdir(folder)):
            src = os.path.join(folder, name)
            if name.startswith(".") or not os.path.isfile(src):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in TYPES:
                sys.exit(f"{prefix}: a file has type {ext!r}, which the bucket does not accept")
            key = f"{prefix}/{clean(name)}"
            if key in keys:
                sys.exit(f"{prefix}: two files map to the same Storage name")
            keys.add(key)
            plan.append({"source": src.replace(HOME, "~", 1), "key": key, "sha256": sha(src),
                         "bytes": os.path.getsize(src), "type": TYPES[ext], "_src": src})
    print(f"files: {len(plan)} in {len(SOURCES)} folders")

    for i, f in enumerate(plan):
        local = os.path.join(up, str(i) + os.path.splitext(f["key"])[1])
        shutil.copy2(f["_src"], local)                       # copy, never move
        if sha(local) != f["sha256"]:
            sys.exit("source file changed while copying; re-run")
        sb("storage", "cp", "--linked", "--experimental", "--content-type", f["type"],
           local, f"ss:///contracts/{f['key']}")
    ok = 0
    for i, f in enumerate(plan):
        back = os.path.join(down, str(i))
        sb("storage", "cp", "--linked", "--experimental", f"ss:///contracts/{f['key']}", back)
        ok += sha(back) == f["sha256"]
    print(f"downloaded back and SHA-256 identical: {ok} / {len(plan)}")

    manifest = [{k: v for k, v in f.items() if k != "_src"} for f in plan]
    tag = "ev" + secrets.token_hex(8)
    body = json.dumps(manifest, ensure_ascii=False)
    sql = (f"insert into public.app_state (doc, key, value) values ('storage_manifest', 'files', ${tag}${body}${tag}$::json) "
           f"on conflict (doc, key) do update set value = excluded.value;")
    path = os.path.join(scratch, "manifest.sql")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(sql)
    sb("db", "query", "--linked", "-f", path)
    print("manifest written to app_state: storage_manifest/files")
    sys.exit(0 if ok == len(plan) else 1)


if __name__ == "__main__":
    main(sys.argv[1])
