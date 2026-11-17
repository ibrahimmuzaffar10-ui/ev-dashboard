#!/usr/bin/env python3
"""Rollback when Supabase itself is DOWN: newest nightly backup -> the old JSON files, without Supabase.

Builds the private local database from the backup (scripts/testdb.py), runs the normal rollback export
(scripts/export_json.py) against it, then deletes the local database. Same output as runbook step R4;
then continue with R5. Needs the mailbox reachable (Zelle keys -> mailbox numbers), like R4.

  .venv/bin/python scripts/restore_local.py <empty output dir>
Data is as of the newest backup (nightly, ~2 AM): anything saved after it must be re-entered by hand.
"""
import os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import testdb  # noqa: E402


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    out = os.path.abspath(sys.argv[1])
    if os.path.exists(out) and os.listdir(out):
        raise SystemExit("output dir must be new or empty (nothing is ever overwritten)")
    env = testdb.start()
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "export_json.py"), out],
                           env=dict(os.environ, EV_BACKEND="supabase", **env))
    finally:
        testdb.stop()
    if r.returncode == 0:
        print(f"restored from the newest backup into {out}; next: runbook R5")
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
