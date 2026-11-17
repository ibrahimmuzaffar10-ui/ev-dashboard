#!/usr/bin/env python3
"""Outbox check / cleanup for the cutover (runbook C7) and rollback (R2). Prints counts and subjects'
lengths only, never addresses or text.

  .venv/bin/python scripts/outbox_admin.py status          counts by status ("empty" if none)
  .venv/bin/python scripts/outbox_admin.py clear --yes     delete EVERY outbox row (cutover only: rows
                                                           left by tests or the shadow run must never be sent)
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["EV_BACKEND"] = "supabase"
import db  # noqa: E402


def status():
    rows = db._read_only(lambda c: c.run("select status, count(*) from public.outbox group by 1 order by 1"))
    print("outbox: " + (", ".join(f"{s} {n}" for s, n in rows) if rows else "empty"))
    return rows


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "status":
        status(); return 0
    if cmd == "clear":
        if "--yes" not in sys.argv:
            sys.exit("refused: add --yes (deletes every outbox row)")
        c = db._connect()
        try:
            c.run("begin"); n = len(c.run("delete from public.outbox returning outbox_id")); c.run("commit")
        finally:
            c.close()
        print(f"deleted {n} outbox rows"); status(); return 0
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
