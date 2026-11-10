#!/usr/bin/env python3
"""Mac job (step 4): copy contract files made online into ~/Documents/Emanant Visuals/<Folder>/,
so Eman's Finder folders stay complete. Runs with the outbox sender (launchd, from cutover).

* Only ADDS files. Never deletes, never overwrites: if a different file already has that name,
  the cloud version is saved next to it as '<name> (cloud copy).<ext>'.
* Every written file is checked against the registry's SHA-256 (written to a temp name first).
* A file macOS won't let this job read (privacy protection on ~/Documents) is left alone.
* EV_SYNC_ROOT=<folder>: write there instead of ~/Documents/Emanant Visuals (tests).

  .venv/bin/python docs_sync.py
"""
import hashlib, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("EV_BACKEND", "supabase")
import db, docstore  # noqa: E402

ROOT = os.path.expanduser(os.environ.get("EV_SYNC_ROOT", docstore.DOCS_TILDE))


def dest_of(source):
    if not source.startswith(docstore.DOCS_TILDE + "/"):
        return None                                   # only files under Emanant Visuals are synced
    return os.path.join(ROOT, source[len(docstore.DOCS_TILDE) + 1:])


def sha_of(path):
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except PermissionError:
        return "unreadable"


def write_checked(path, data, sha):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = os.path.join(os.path.dirname(path), "." + os.path.basename(path) + ".part")
    with open(tmp, "wb") as fh:
        fh.write(data)
    if sha_of(tmp) != sha:
        os.remove(tmp)
        raise RuntimeError("written file does not match")
    os.replace(tmp, path)


def main():
    added = cloud_copies = same = skipped = errors = 0
    for m in db.file_registry():
        dest = dest_of(m["source"])
        if not dest:
            skipped += 1; continue
        copy = False
        if os.path.exists(dest):
            if sha_of(dest) in (m["sha256"], "unreadable"):
                same += 1; continue
            stem, ext = os.path.splitext(dest)
            dest, copy = f"{stem} (cloud copy){ext}", True
            if os.path.exists(dest):
                same += 1; continue
        got = db.file_get(m["key"])
        if not got:
            errors += 1; print("missing in the database:", m["key"]); continue
        try:
            write_checked(dest, got[1], m["sha256"])
            cloud_copies += copy; added += not copy
        except Exception as ex:
            errors += 1; print("could not write", m["key"], ex)
    print(f"docs sync: {added} added, {cloud_copies} saved as cloud copy, {same} already there, {skipped} not synced, {errors} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
