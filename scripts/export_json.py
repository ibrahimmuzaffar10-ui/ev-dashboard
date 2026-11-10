#!/usr/bin/env python3
"""Rollback tool (step 6): write everything in Supabase back out as the old JSON files, so the
old Mac dashboard can take over again. Writes ONLY into the folder you give (never ~/EmanantHQ
unless you pass it on purpose during a real rollback). Prints counts only.

  .venv/bin/python scripts/export_json.py <folder>

Files: tracker_data.json (no changelog: dropped 11/10), payments.json, watch_state.json (seen =
emails handled, last 3000), brief_latest.json, brief_state.json, brief_ack.json.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["EV_BACKEND"] = "supabase"
import db  # noqa: E402

MAX_TRIES = 3


def write(folder, name, obj, **dump):
    p = os.path.join(folder, name + ".json")
    tmp = p + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(obj, fh, **dump)
    os.replace(tmp, p)


def main(folder):
    os.makedirs(folder, exist_ok=True)
    t = db.load()
    pays = db.payments_all()
    meta = db.read_doc("watch_state") or {}
    rows = db.email_rows()
    seen = sorted((k for k, (s, n) in rows.items() if s in ("processed", "skipped") or (s == "failed" and n >= MAX_TRIES)),
                  key=lambda k: k.encode("utf-8"))[-3000:]
    retry = {k: n for k, (s, n) in rows.items() if s == "failed" and n < MAX_TRIES}
    ws = {"since": meta.get("since"), "seen": seen, "last_run": meta.get("last_run"), "last_ok": meta.get("last_ok")}
    if retry:
        ws["retry"] = retry
    write(folder, "tracker_data", t, indent=1, ensure_ascii=False)
    write(folder, "payments", pays, indent=1)
    write(folder, "watch_state", ws)
    for name in ("brief_latest", "brief_state", "brief_ack"):
        d = db.read_doc(name)
        if d is not None:
            write(folder, name, d, ensure_ascii=False)
    print(f"exported: leads {len(t['leads'])}, alerts {len(t.get('alerts', []))}, vendors {len(t['vendors'])}, "
          f"payments {len(pays)}, emails seen {len(seen)} (+{len(retry)} to retry)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(os.path.expanduser(sys.argv[1]))
