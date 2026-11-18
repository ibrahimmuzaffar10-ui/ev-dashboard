"""Web push to the phone app (Phase 16). Runs on the Mac only: the VAPID private key lives in .env.local.

send(title, body, url) -> number of devices reached. Never raises: a push problem must never stop the email
watcher or the outbox. Devices the push service reports as gone (404/410) are removed. Test/shadow runs and
EV_PUSH_OFF=1 send nothing.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evenv  # noqa: E402,F401
import db  # noqa: E402


def _off():
    return (os.environ.get("EV_SHADOW") == "1" or os.environ.get("EV_PUSH_OFF") == "1"
            or (os.environ.get("EV_TEST_DB") == "1" and os.environ.get("EV_PUSH_TEST_OK") != "1"))


def _vapid():
    from py_vapid import Vapid01
    return Vapid01.from_der(os.environ["EV_VAPID_PRIVATE_KEY"].encode())   # base64url DER, as stored in .env.local


def _write(sql, **kw):
    c = db._connect()
    try:
        c.run("begin"); c.run(sql, **kw); c.run("commit")
    finally:
        c.close()


def send(title, body, url="/inbox", tag=None):
    if _off() or not db.CLOUD or not os.environ.get("EV_VAPID_PRIVATE_KEY"):
        return 0
    try:
        from pywebpush import webpush, WebPushException
        subs = db._read_only(lambda c: c.run("select id, endpoint, p256dh, auth from public.push_subscriptions"))
        if not subs:
            return 0
        vapid = _vapid()
        claims = {"sub": os.environ.get("EV_VAPID_SUBJECT", "https://emanantvisuals-hq.vercel.app")}
        data = json.dumps({"title": str(title)[:120], "body": str(body)[:240], "url": url, "tag": tag}, ensure_ascii=False)
        ok = 0
        for sid, endpoint, p256dh, auth in subs:
            # the test database is a copy of the live one, real phones included: tests may only reach a local fake
            if os.environ.get("EV_TEST_DB") == "1" and not str(endpoint).startswith("http://127.0.0.1:"):
                continue
            try:
                webpush({"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}, data,
                        vapid_private_key=vapid, vapid_claims=dict(claims), ttl=24 * 3600, timeout=10)
                _write("update public.push_subscriptions set last_ok_at = now() where id = :i", i=sid)
                ok += 1
            except WebPushException as ex:
                code = getattr(ex.response, "status_code", None)
                if code in (404, 410):              # unsubscribed / app removed: forget this device
                    _write("delete from public.push_subscriptions where id = :i", i=sid)
                print("push not delivered:", code or str(ex)[:80])
            except Exception as ex:
                print("push not delivered:", str(ex)[:80])
        return ok
    except Exception as ex:
        print("push skipped:", str(ex)[:120])
        return 0
