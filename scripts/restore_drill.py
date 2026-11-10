#!/usr/bin/env python3
"""Restore drill (step 6): prove a nightly backup really restores.
Builds a throwaway local PostgreSQL 17 from scratch (Supabase stand-in + every migration in git),
restores the backup's data into it, and compares every app table row by row with live Supabase.
Leaves nothing running; deletes the throwaway database. Prints counts and PASS/FAIL only.

  .venv/bin/python scripts/restore_drill.py <backup.dump> <scratch dir>
Run it when nothing is writing to Supabase, or the live side may have moved on.
"""
import glob, hashlib, os, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["EV_BACKEND"] = "supabase"
import db  # noqa: E402

PG = os.environ.get("EV_PG_BIN", "/opt/homebrew/opt/postgresql@17/bin")
DUMP, SCRATCH = sys.argv[1], sys.argv[2]
DATA, PORT = os.path.join(SCRATCH, "pgdrill"), "54329"
SOCK = os.path.expanduser("~/Library/Caches/emanant-hq/pgsock")   # short: macOS caps socket paths at 103 bytes
os.makedirs(SOCK, mode=0o700, exist_ok=True)
ENV = dict(os.environ, PGTZ="UTC", PGHOST=SOCK, PGPORT=PORT, PGUSER="postgres")
results = []


def run(*args, ok=True):
    r = subprocess.run(list(args), env=ENV, capture_output=True, text=True, timeout=900)
    if ok and r.returncode != 0:
        raise SystemExit(f"{os.path.basename(args[0])} failed: {r.stderr.strip()[-400:]}")
    return r


def psql(sql_or_file, db_="drill", file=False):
    return run(os.path.join(PG, "psql"), "-X", "-q", "-v", "ON_ERROR_STOP=1", "-At", "-d", db_, *(["-f", sql_or_file] if file else ["-c", sql_or_file]))


FP = "select count(*) || ':' || coalesce(md5(string_agg(t::text, '|' order by t::text collate \"C\")), '') from public.{} t"


try:
    shutil.rmtree(DATA, ignore_errors=True)
    run(os.path.join(PG, "initdb"), "-D", DATA, "-U", "postgres", "--auth=trust", "-E", "UTF8", "--locale=C")
    run(os.path.join(PG, "pg_ctl"), "-D", DATA, "-o", f"-p {PORT} -k {SOCK} -c listen_addresses=''", "-l", os.path.join(SCRATCH, "pgdrill.log"), "-w", "start")
    psql("create database drill", db_="postgres")
    psql(os.path.join(ROOT, "supabase", "tests", "supabase_stub.sql"), file=True)
    migs = sorted(glob.glob(os.path.join(ROOT, "supabase", "migrations", "*.sql")))
    for m in migs:
        psql(m, file=True)
    results.append(("schema rebuilt from git: stand-in + migrations", "PASS", f"{len(migs)} migrations"))
    run(os.path.join(PG, "pg_restore"), "--data-only", "--disable-triggers", "--no-owner", "-d", "drill", DUMP)
    tables = [t for t in psql("select tablename from pg_tables where schemaname = 'public' order by 1").stdout.split()]
    live = db._read_only(lambda c: [c.run("set local timezone = 'UTC'")] and {t: c.run(FP.format(t))[0][0] for t in tables})
    same = 0
    for t in tables:
        here = psql(FP.format(t)).stdout.strip()
        ok = here == live[t]
        same += ok
        results.append((f"  {t}", "PASS" if ok else "FAIL", f"{here.split(':')[0]} rows"))
    results.append(("every table restored identical to live Supabase", "PASS" if same == len(tables) else "FAIL", f"{same}/{len(tables)}"))
    seq = psql("select count(*) from pg_sequences where schemaname = 'public' and last_value is not null").stdout.strip()
    results.append(("ID counters restored (no restart at 1)", "PASS" if int(seq or 0) > 0 else "FAIL", f"{seq} counters"))
finally:
    run(os.path.join(PG, "pg_ctl"), "-D", DATA, "-m", "fast", "stop", ok=False)
    shutil.rmtree(DATA, ignore_errors=True)

width = max(len(r[0]) for r in results)
for name, res, got in results:
    print(f"{name:<{width}}  {res}  {got}")
fails = sum(r[1] == "FAIL" for r in results)
print(f"\n{len(results) - fails} pass, {fails} fail")
sys.exit(1 if fails else 0)
