#!/usr/bin/env python3
"""Mac email sender for the cloud outbox (step 3). Runs every minute (launchd, from cutover).

For each queued email: claim it (status 'sending'), send it from Eman's iCloud, mark it 'sent'.
* Failure before/while sending: back to 'queued' with a growing wait (1, 2, 4, 8 min); after 5
  tries 'failed' and a dashboard alert.
* Interrupted send (left in 'sending' > 15 min, e.g. the Mac slept mid-send): NEVER re-sent
  automatically, because it may already have gone out. It becomes 'unknown' and an alert asks a
  person to check Sent and resend by hand if needed.
* One run at a time (lock file). EV_OUTBOX_DRY=<folder>: write .eml files there instead of sending.

  .venv/bin/python outbox_send.py
"""
import datetime, fcntl, json, os, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("EV_BACKEND", "supabase")
import db, evenv, mailer  # noqa: E402

API = os.environ.get("EV_API", "http://127.0.0.1:8787")
DRY = os.environ.get("EV_OUTBOX_DRY")
MAX_TRIES = 5
STALE_MIN = 15
LOCK_PATH = os.path.expanduser(os.environ.get("EV_OUTBOX_LOCK", "~/Library/Caches/emanant-hq/outbox.lock"))


def alert(title, detail, key):
    """Tell a person on the dashboard (deduped by key). Never raises."""
    try:
        req = urllib.request.Request(API + "/api/alert-new", headers={"Content-Type": "application/json"}, data=json.dumps(
            {"type": "unclear", "title": title[:200], "detail": detail[:600], "email_id": key}).encode())
        urllib.request.urlopen(req, timeout=30).read()
        return True
    except Exception as ex:
        print("alert failed:", ex)
        return False


def tx(c, sql, **kw):
    c.run("begin")
    try:
        out = c.run(sql, **kw)
        c.run("commit")
        return out
    except Exception:
        c.run("rollback")
        raise


def send_one(c, row):
    oid, mid, to, subject, body, reply = row
    files = [(n, t, bytes(d)) for n, t, d in c.run(
        "select filename, content_type, data from public.outbox_files where outbox_id = :o order by position", o=oid)]
    to = evenv.need("EV_FROM_EMAIL") if to == mailer.SELF else to
    msg = mailer.build(to, subject, body, reply, files, message_id=mid)
    if DRY:
        os.makedirs(DRY, exist_ok=True)
        with open(os.path.join(DRY, f"{oid}.eml"), "wb") as fh:
            fh.write(msg.as_bytes())
    else:
        mailer.send(msg)


def main():
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    lock = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another run is still going; skipped"); return
    c = db._connect()
    sent = failed = 0
    try:
        # interrupted sends: never re-send automatically
        for oid, subject in tx(c, "update public.outbox set status = 'unknown', last_error = 'interrupted while sending' "
                                  "where status = 'sending' and claimed_at < now() - make_interval(mins => :m) returning outbox_id, subject", m=STALE_MIN):
            alert("Email may not have been sent: check Sent", f"“{subject}” was interrupted while sending. Check Mail › Sent; resend by hand if it isn't there.", f"outbox-unknown:{oid}")
        while True:
            got = tx(c, "update public.outbox set status = 'sending', claimed_at = now(), attempts = attempts + 1 "
                        "where outbox_id = (select outbox_id from public.outbox where status = 'queued' and next_try_at <= now() "
                        "                   order by outbox_id limit 1 for update skip locked) "
                        "returning outbox_id, message_id, to_addr, subject, body, in_reply_to, attempts")
            if not got:
                break
            row, attempts = got[0][:6], got[0][6]
            try:
                c.run("begin"); send_one(c, row); c.run("commit")
            except Exception as ex:
                try: c.run("rollback")
                except Exception: pass
                err = str(ex)[:300]
                if attempts >= MAX_TRIES:
                    tx(c, "update public.outbox set status = 'failed', last_error = :e where outbox_id = :o", e=err, o=row[0])
                    alert("Email could not be sent", f"“{row[3]}” failed {attempts} times: {err}", f"outbox-failed:{row[0]}")
                else:
                    tx(c, "update public.outbox set status = 'queued', last_error = :e, "
                          "next_try_at = now() + make_interval(mins => :w) where outbox_id = :o", e=err, w=2 ** (attempts - 1), o=row[0])
                failed += 1
                continue
            tx(c, "update public.outbox set status = 'sent', sent_at = now(), last_error = null where outbox_id = :o", o=row[0])
            sent += 1
    finally:
        c.close()
    print(f"{datetime.datetime.now():%Y-%m-%d %H:%M} outbox: {sent} sent, {failed} failed")


if __name__ == "__main__":
    main()
