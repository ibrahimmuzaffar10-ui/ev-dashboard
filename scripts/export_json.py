#!/usr/bin/env python3
"""Rollback tool (step 6): write everything in Supabase back out as the old JSON files, so the
old Mac dashboard can take over again. Writes ONLY into the folder you give (never ~/EmanantHQ
unless you pass it on purpose during a real rollback). Prints counts only.

  .venv/bin/python scripts/export_json.py <folder>

Files: tracker_data.json (no changelog: dropped 11/10), payments.json, watch_state.json (seen =
emails handled, last 3000), brief_latest.json, brief_state.json, brief_ack.json.

Keys are translated back to what the OLD scripts expect (review fix #1):
  - Zelle payments: the cloud keys them by Message-ID; the old importer dedupes on the mailbox number.
    Each Message-ID is looked up in the mailbox (read-only himalaya search) and written back as the
    mailbox number, or the old importer would import every cloud-period payment again (double money).
    A payment whose email is no longer in the mailbox keeps its Message-ID: the old importer can't
    see that email either, so it can't duplicate it. If the mailbox can't be read, the export STOPS.
  - Emails without a Message-ID: the cloud writes "inbox:<n>" / "junk:<n>"; the old watcher uses "<n>".
"""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["EV_BACKEND"] = "supabase"
import db  # noqa: E402
import evenv  # noqa: E402

MAX_TRIES = 3


def zelle_mailbox_numbers():
    """{Message-ID: mailbox number} for the bank's Zelle emails, read-only. Raises if the mailbox can't be read."""
    sender = evenv.need("EV_ZELLE_SENDER")
    r = subprocess.run(["himalaya", "--json", "envelope", "search", "-s", "2000",
                        f'from {sender} and subject "You received money with Zelle" order by date desc'],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise SystemExit("export stopped: can't read the mailbox to translate Zelle keys (" + r.stderr.strip()[-200:] + ")")
    j = json.loads(r.stdout)
    envs = j["envelopes"] if isinstance(j, dict) else j
    return {e["message-id"]: e["id"] for e in envs if e.get("message-id")}


def old_watch_key(k):
    """'inbox:123' / 'junk:123' -> '123' (the old watcher's key for an email without a Message-ID)."""
    for pre in ("inbox:", "junk:"):
        if k.startswith(pre):
            return k[len(pre):]
    return k


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
    mids = {p["email_id"] for p in pays if "@" in str(p.get("email_id") or "")}
    mailbox = zelle_mailbox_numbers() if mids else {}
    translated = kept = 0
    for p in pays:
        k = str(p.get("email_id") or "")
        if k in mailbox:
            p["email_id"] = mailbox[k]; translated += 1
        elif k in mids:
            kept += 1
    meta = db.read_doc("watch_state") or {}
    rows = db.email_rows()
    seen = sorted({old_watch_key(k) for k, (s, n) in rows.items() if s in ("processed", "skipped") or (s == "failed" and n >= MAX_TRIES)},
                  key=lambda k: k.encode("utf-8"))[-3000:]
    retry = {old_watch_key(k): n for k, (s, n) in rows.items() if s == "failed" and n < MAX_TRIES}
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
          f"payments {len(pays)} (Zelle keys -> mailbox numbers: {translated}, email gone so kept: {kept}), emails seen {len(seen)} (+{len(retry)} to retry)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(os.path.expanduser(sys.argv[1]))
