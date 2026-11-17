#!/usr/bin/env python3
"""Mac email sender for the cloud outbox (step 3). Runs every minute (launchd, from cutover).

For each queued email: claim it (status 'sending'), send it from Eman's iCloud, mark it 'sent'.
* Failure before/while sending: back to 'queued' with a growing wait (1, 2, 4, 8 min); after 5
  tries 'failed' and a dashboard alert.
* Interrupted send (left in 'sending' > 15 min, e.g. the Mac slept mid-send): NEVER re-sent
  automatically, because it may already have gone out. It becomes 'unknown' and an alert asks a
  person to check Sent and resend by hand if needed.
* No connection (Wi-Fi down, iCloud unreachable): back to 'queued' in 2 min WITHOUT using up a try.
* Connection broke while handing the email over: it may have gone out, so 'unknown' + alert (never
  re-sent automatically). Anything after iCloud accepted it (QUIT, Sent copy) counts as sent.
* Waited too long (EV_OUTBOX_MAX_AGE_H, default 12 h, e.g. the Mac was off): NOT sent late
  automatically; 'failed' + alert, and the dashboard's "Send again" sends it if it's still right.
* Nothing is held open in the database while sending.
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
MAX_AGE_H = float(os.environ.get("EV_OUTBOX_MAX_AGE_H", "12"))
LOCK_PATH = os.path.expanduser(os.environ.get("EV_OUTBOX_LOCK", "~/Library/Caches/emanant-hq/outbox.lock"))
# emails that CERTAINLY did not go out but couldn't be put back in the queue (the database was
# unreachable too, e.g. Wi-Fi dropped): remembered here and re-queued first thing next run, so they
# don't turn into a false "may have been sent" alert 15 minutes later
JOURNAL = LOCK_PATH + ".notsent.json"


def journal(add=None):
    try:
        ids = set(json.load(open(JOURNAL)))
    except Exception:
        ids = set()
    if add is None:
        return ids
    ids.add(add)
    with open(JOURNAL, "w") as fh:
        json.dump(sorted(ids), fh)


def alert(title, detail, key):
    """Tell a person on the dashboard (deduped by key). Never raises."""
    try:
        req = urllib.request.Request(API + "/api/alert-new", headers={"Content-Type": "application/json", "X-EV-Job": os.environ.get("EV_JOB_TOKEN", "")}, data=json.dumps(
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
    """Build and send one email. Attachments are read in their own short transaction, so no
    database transaction is open while talking to iCloud."""
    oid, mid, to, subject, body, reply = row
    files = [(n, t, bytes(d)) for n, t, d in tx(c,
        "select filename, content_type, data from public.outbox_files where outbox_id = :o order by position", o=oid)]
    to = evenv.need("EV_FROM_EMAIL") if to == mailer.SELF else to
    msg = mailer.build(to, subject, body, reply, files, message_id=mid)
    if DRY:
        if os.environ.get("EV_OUTBOX_DRY_FAIL") == "network":
            raise mailer.NotSent("test: no connection", network=True)
        if os.environ.get("EV_OUTBOX_DRY_FAIL") == "maybe":
            raise mailer.MaybeSent("test: connection broke while sending")
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
        ids = journal()
        if ids:                                   # certainly-not-sent emails from a run that lost the database
            tx(c, "update public.outbox set status = 'queued', attempts = greatest(attempts - 1, 0), next_try_at = now(), "
                  "last_error = 'not sent (connection lost); queued again' where status = 'sending' and outbox_id = any(:ids)", ids=list(ids))
            os.remove(JOURNAL)
        # interrupted sends: never re-send automatically
        for oid, subject, gen in tx(c, "update public.outbox set status = 'unknown', last_error = 'interrupted while sending' "
                                  "where status = 'sending' and claimed_at < now() - make_interval(mins => :m) "
                                  "returning outbox_id, subject, extract(epoch from created_at)::bigint", m=STALE_MIN):
            alert("Email may not have been sent: check Sent", f"“{subject}” was interrupted while sending. Check Mail › Sent; resend by hand if it isn't there.", f"outbox-unknown:{oid}:{gen}")
        # waited too long (Mac off for hours): don't send late without a person deciding
        for oid, subject, gen in tx(c, "update public.outbox set status = 'failed', last_error = 'waited too long: not sent automatically' "
                                  "where status = 'queued' and created_at < now() - (:h * interval '1 hour') "
                                  "returning outbox_id, subject, extract(epoch from created_at)::bigint", h=MAX_AGE_H):
            alert("Email not sent: waited too long", f"“{subject}” waited over {MAX_AGE_H:g} hours (the Mac was offline) and was not sent "
                  "automatically. Check it is still right, then use Send again on the dashboard (Emails waiting).", f"outbox-old:{oid}:{gen}")
        while True:
            got = tx(c, "update public.outbox set status = 'sending', claimed_at = now(), attempts = attempts + 1 "
                        "where outbox_id = (select outbox_id from public.outbox where status = 'queued' and next_try_at <= now() "
                        "                   order by outbox_id limit 1 for update skip locked) "
                        "returning outbox_id, message_id, to_addr, subject, body, in_reply_to, attempts, extract(epoch from created_at)::bigint")
            if not got:
                break
            row, attempts, gen = got[0][:6], got[0][6], got[0][7]
            try:
                try:
                    send_one(c, row)
                except SystemExit as ex:              # a missing setting (evenv.need) before anything was sent
                    raise mailer.NotSent(f"setting missing: {ex}")
            except mailer.MaybeSent as ex:
                tx(c, "update public.outbox set status = 'unknown', last_error = :e where outbox_id = :o", e=str(ex)[:300], o=row[0])
                alert("Email may not have been sent: check Sent", f"“{row[3]}”: {str(ex)[:200]}. Check Mail › Sent; use Send again only if it isn't there.", f"outbox-unknown:{row[0]}:{gen}")
                failed += 1
                continue
            except mailer.NotSent as ex:
                if ex.network:              # offline: try again soon, don't use up a try; stop this run
                    try:
                        tx(c, "update public.outbox set status = 'queued', attempts = attempts - 1, last_error = :e, "
                              "next_try_at = now() + interval '2 minutes' where outbox_id = :o", e=str(ex)[:300], o=row[0])
                    except Exception:
                        journal(row[0])     # database gone too: re-queue next run (it certainly wasn't sent)
                    failed += 1
                    break
                err = str(ex)[:300]
            except Exception as ex:
                err = str(ex)[:300]
            else:
                tx(c, "update public.outbox set status = 'sent', sent_at = now(), last_error = null where outbox_id = :o", o=row[0])
                sent += 1
                continue
            if attempts >= MAX_TRIES:
                tx(c, "update public.outbox set status = 'failed', last_error = :e where outbox_id = :o", e=err, o=row[0])
                alert("Email could not be sent", f"“{row[3]}” failed {attempts} times: {err}", f"outbox-failed:{row[0]}:{gen}")
            else:
                tx(c, "update public.outbox set status = 'queued', last_error = :e, "
                      "next_try_at = now() + make_interval(mins => :w) where outbox_id = :o", e=err, w=2 ** (attempts - 1), o=row[0])
            failed += 1
    finally:
        c.close()
    try:
        import evtime
        db.doc_write("heartbeat_outbox", {"at": evtime.now_ct().isoformat(timespec="seconds"), "sent": sent, "failed": failed})
        ping_if_watcher_healthy()
    except Exception as ex:
        print("heartbeat not saved:", ex)
    print(f"{datetime.datetime.now():%Y-%m-%d %H:%M} outbox: {sent} sent, {failed} failed")
    check_now()


def ping_if_watcher_healthy():
    """healthchecks.io "email watcher" check (15-min period): the email check now runs every 2 h, so this
    1-min job pings for it, but ONLY while the watcher's last run succeeded within 2.5 h. Mac off, Supabase
    unreachable or a failing watcher (e.g. the iCloud app password expired) -> no ping -> Ibrahim gets an email."""
    import evtime
    url = os.environ.get("EV_HEALTHCHECK_URL")
    hw = db.read_doc("heartbeat_watch") or {}
    try:
        age = (evtime.now_ct() - datetime.datetime.fromisoformat(hw["at"])).total_seconds()
    except Exception:
        return
    testing = os.environ.get("EV_TEST_DB") == "1" or os.environ.get("EV_OUTBOX_DRY")
    if url and not testing and hw.get("ok") and not hw.get("shadow") and age <= 2.5 * 3600:
        try: urllib.request.urlopen(url, timeout=10).read()
        except Exception as ex: print("healthcheck ping failed:", ex)


KICK_STAMP = os.path.expanduser("~/Library/Caches/emanant-hq/check_now.kicked")


def check_now():
    """"Check email now" from the dashboard (Mac or website): if a request is newer than the watcher's last
    run, start the watcher. At most one start per 5 min (a run takes ~1 min; offline it would fail anyway),
    and requests older than 6 h are dropped (the regular 2-hour run has covered them). Never fails the run."""
    try:
        import evtime, subprocess, time
        req = (db.read_doc("check_request") or {}).get("at")
        last = (db.read_doc("heartbeat_watch") or {}).get("at") or ""
        if not req or req <= last:
            return
        now = evtime.now_ct()
        if (now - datetime.datetime.fromisoformat(req)).total_seconds() > 6 * 3600:
            return
        try:
            if time.time() - os.path.getmtime(KICK_STAMP) < 300:
                return
        except OSError:
            pass
        os.makedirs(os.path.dirname(KICK_STAMP), exist_ok=True)
        open(KICK_STAMP, "w").close()
        r = subprocess.run(["launchctl", "kickstart", f"gui/{os.getuid()}/com.emanantvisuals.watch"], capture_output=True, text=True)
        print("check-now: watcher started" if r.returncode == 0 else "check-now: could not start watcher: " + r.stderr.strip()[:120])
    except Exception as ex:
        print("check-now skipped:", ex)


if __name__ == "__main__":
    main()
