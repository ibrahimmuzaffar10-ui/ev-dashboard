#!/usr/bin/env python3
"""Nightly backup (step 6): pg_dump of every app table (schema + data, schema `public`) from
Supabase to this Mac, as the limited ev_server login over a verified TLS connection.
Keeps the newest 30. Backups live under ~/Library/Application Support/emanant-hq/backups
(FileVault-encrypted disk), files readable only by this user. Prints sizes/counts only.

Not in this backup (by design): Supabase login accounts and the allowlist (2 users, recreated by
hand), and the Storage archive copy (never changes; the files themselves are in `public.files`).

  .venv/bin/python scripts/backup.py            -> path of the new backup
  EV_BACKUP_DIR=<folder> to write elsewhere (tests)
"""
import datetime, glob, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import evenv  # noqa: E402

PG = os.environ.get("EV_PG_BIN", "/opt/homebrew/opt/postgresql@17/bin")
OUT = os.path.expanduser(os.environ.get("EV_BACKUP_DIR", "~/Library/Application Support/emanant-hq/backups"))
KEEP = 30


def conninfo():
    ca = os.path.join(ROOT, "supabase", "supabase-ca.crt")
    # session pooler (port 5432): pg_dump needs a session, not the transaction pooler
    return (f"host={evenv.need('EV_DB_HOST')} port=5432 dbname=postgres user={evenv.need('EV_DB_USER')} "
            f"sslmode=verify-full sslrootcert={ca}")


def main():
    os.makedirs(OUT, mode=0o700, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    path = os.path.join(OUT, f"ev-dashboard_{stamp}.dump")
    env = dict(os.environ, PGPASSWORD=evenv.need("EV_DB_PASSWORD"))
    r = subprocess.run([os.path.join(PG, "pg_dump"), "--dbname", conninfo(), "--schema", "public", "--format", "custom",
                        "--enable-row-security", "--no-owner", "--file", path + ".part"], env=env, capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        if os.path.exists(path + ".part"):
            os.remove(path + ".part")
        sys.exit("backup FAILED: " + r.stderr.strip()[-400:])
    os.chmod(path + ".part", 0o600)
    os.replace(path + ".part", path)
    lst = subprocess.run([os.path.join(PG, "pg_restore"), "--list", path], capture_output=True, text=True)
    tables = sum(1 for l in lst.stdout.splitlines() if " TABLE DATA public " in l)
    old = sorted(glob.glob(os.path.join(OUT, "ev-dashboard_*.dump")))[:-KEEP]
    for f in old:
        os.remove(f)                                  # only our own old backups
    print(f"backup OK: {path} ({os.path.getsize(path) // 1024} KB, {tables} tables with data; {len(old)} old removed)")
    return path


if __name__ == "__main__":
    main()
