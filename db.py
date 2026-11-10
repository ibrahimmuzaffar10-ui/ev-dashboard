"""Data layer for server.py.

EV_BACKEND=json      (default) today's JSON files, unchanged.
EV_BACKEND=supabase  Postgres via the Supabase pooler, as the `ev_server` role.

Save path (supabase):  with db.locked(LOCK): d = load(); <route code>; store(d)
  * locked() opens ONE transaction and takes a transaction-level advisory lock, so saves from
    every server instance (Mac, Vercel) run one at a time, like the old threading.Lock.
  * store() writes inserts, updates AND deletes (alert folding), then COMMITS, before the route
    sends its 200. If the commit fails the route returns an error instead of a false success.
  * Items are written as JSON TEXT into `json` columns (never jsonb), so key order, missing vs
    null and 500 vs 500.0 survive exactly. No changelog (dropped 11/10).
  * No session state is used (no prepared statements, no session locks): safe on the
    transaction pooler (port 6543).
"""
import json, os, ssl, threading

import evenv  # noqa: F401  (loads .env.local)

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.environ.get("EV_BACKEND", "json")
CLOUD = BACKEND == "supabase"
LISTS = ("leads", "vendors", "alerts")
KEYED = {"leads": "id", "alerts": "id"}            # vendors have no id: rewritten as a whole
LOCK_KEY = 0x45564851                              # 'EVHQ'
_tls = threading.local()


def j(v):
    return json.dumps(v, ensure_ascii=False, allow_nan=False)


def _connect():
    import pg8000.native as pg
    ca = os.path.expanduser(os.environ.get("EV_DB_CA", os.path.join(HERE, "supabase", "supabase-ca.crt")))
    return pg.Connection(user=evenv.need("EV_DB_USER"), password=evenv.need("EV_DB_PASSWORD"),
                         host=evenv.need("EV_DB_HOST"), port=int(os.environ.get("EV_DB_PORT", "6543")),
                         database="postgres", ssl_context=ssl.create_default_context(cafile=ca), timeout=20)


# ------------------------------------------------------------------ transactions
class locked:
    """json: the old threading.Lock.  supabase: one transaction + advisory lock."""

    def __init__(self, lock):
        self.lock = lock

    def __enter__(self):
        if not CLOUD:
            self.lock.acquire()
            return self
        c = _connect()
        try:
            c.run("begin")
            c.run("select pg_advisory_xact_lock(:k)", k=LOCK_KEY)
        except Exception:
            c.close()
            raise
        _tls.tx = {"conn": c, "snap": None, "done": False}
        return self

    def __exit__(self, et, ev, tb):
        if not CLOUD:
            self.lock.release()
            return False
        tx = _tls.__dict__.pop("tx", None)
        if tx:
            try:
                if not tx["done"]:
                    tx["conn"].run("rollback")          # no store(): nothing to keep
            finally:
                tx["conn"].close()
        return False


# ------------------------------------------------------------------ reads
def _read(c):
    snap, d_lists = {}, {}
    for t in LISTS:
        rows = c.run(f"select pos, raw::text from public.{t} order by pos")
        items = [json.loads(r) for _, r in rows]
        d_lists[t] = items
        if t in KEYED:
            snap[t] = {o[KEYED[t]]: (p, r) for (p, r), o in zip(rows, items)}
        else:
            snap[t] = [r for _, r in rows]
    st = {k: v for k, v in c.run("select key, value::text from public.app_state where doc = 'tracker_data'")}
    snap["app"] = st
    order = json.loads(st.get("_key_order", "[]"))
    d = {}
    for k in order:
        d[k] = d_lists[k] if k in LISTS else json.loads(st[k])
    for t in LISTS:                                 # a list missing from _key_order still loads
        d.setdefault(t, d_lists[t])
    return d, snap


def load():
    tx = getattr(_tls, "tx", None)
    if tx:
        d, tx["snap"] = _read(tx["conn"])
        return d
    c = _connect()
    try:
        c.run("begin transaction isolation level repeatable read read only")
        d, _ = _read(c)
        c.run("commit")
        return d
    finally:
        c.close()


def _read_only(fn):
    c = _connect()
    try:
        c.run("begin transaction isolation level repeatable read read only")
        out = fn(c)
        c.run("commit")
        return out
    finally:
        c.close()


def payments():
    return _read_only(lambda c: [json.loads(r) for (r,) in c.run("select raw::text from public.payments order by pos")])


def read_doc(name):
    """A whole small file (brief_latest, brief_ack, ...) rebuilt from app_state, or None."""
    def go(c):
        st = {k: v for k, v in c.run("select key, value::text from public.app_state where doc = :d", d=name)}
        if not st:
            return None
        if "" in st and "_key_order" not in st:
            return json.loads(st[""])
        return {k: json.loads(st[k]) for k in json.loads(st["_key_order"])}
    return _read_only(go)


def write_doc(name, obj):
    """Replace a whole small file in app_state, in its own transaction."""
    c = _connect()
    try:
        c.run("begin")
        c.run("delete from public.app_state where doc = :d", d=name)
        rows = [("_key_order", j(list(obj)))] + [(k, j(v)) for k, v in obj.items()] if isinstance(obj, dict) else [("", j(obj))]
        for k, v in rows:
            c.run("insert into public.app_state (doc, key, value) values (:d, :k, cast(:v as json))", d=name, k=k, v=v)
        c.run("commit")
    finally:
        c.close()


# ------------------------------------------------------------------ writes
def store(d):
    tx = getattr(_tls, "tx", None)
    if not tx or tx["snap"] is None:
        raise RuntimeError("store() outside a locked load()")
    if tx["done"]:
        raise RuntimeError("store() called twice in one request")
    c, snap = tx["conn"], tx["snap"]

    for t, key in KEYED.items():
        new = [(o[key], i, j(o)) for i, o in enumerate(d.get(t, []))]
        ids = [k for k, _, _ in new]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate {t} id")
        old, keep = snap[t], set(ids)
        gone = [k for k in old if k not in keep]
        if gone:
            c.run(f"delete from public.{t} where id = any(cast(:ids as text[]))", ids=gone)
        for k, i, txt in new:
            if k not in old:
                c.run(f"insert into public.{t} (pos, raw) values (:p, cast(:r as json))", p=i, r=txt)
            elif old[k] != (i, txt):
                c.run(f"update public.{t} set pos = :p, raw = cast(:r as json) where id = :k", p=i, r=txt, k=k)

    vendors = [j(o) for o in d.get("vendors", [])]
    if vendors != snap["vendors"]:
        c.run("delete from public.vendors")
        for i, txt in enumerate(vendors):
            c.run("insert into public.vendors (pos, raw) values (:p, cast(:r as json))", p=i, r=txt)

    order = [k for k in d if k != "changelog"]
    want = {k: j(d[k]) for k in order if k not in LISTS}
    want["_key_order"] = j(order)
    have = snap["app"]
    for k in have:
        if k not in want:
            c.run("delete from public.app_state where doc = 'tracker_data' and key = :k", k=k)
    for k, v in want.items():
        if have.get(k) != v:
            c.run("insert into public.app_state (doc, key, value) values ('tracker_data', :k, cast(:v as json)) "
                  "on conflict (doc, key) do update set value = excluded.value", k=k, v=v)

    c.run("commit")                                 # before the route answers 200
    tx["done"] = True


def user_is_allowed(uid):
    """True only if this Supabase user id is on the allowlist (asks about one id; cannot list it)."""
    return bool(_read_only(lambda c: c.run("select private.user_is_allowed(cast(:u as uuid))", u=uid)[0][0]))
