"""Data layer for server.py. (Supabase reads use schema v2 since 11/10; see legacy.py.)

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
def _rows(c, sql, **kw):
    out = c.run(sql, **kw)
    cols = [x["name"] for x in c.columns]
    return [dict(zip(cols, r)) for r in out]


def _group(rows, key):
    g = {}
    for r in rows:
        g.setdefault(r[key], []).append(r)
    return g


def _read(c):
    """Schema v2 (normalized) -> the old tracker_data shape the route code expects (see legacy.py)."""
    import legacy
    clients = {r["client_id"]: r for r in _rows(c, "select * from public.clients")}
    contracts = {r["lead_id"]: r for r in _rows(c, "select * from public.contracts")}
    plan = _group(_rows(c, "select * from public.contract_plan_items"), "contract_id")
    docs = _group(_rows(c, "select * from public.documents"), "contract_id")
    days = _group(_rows(c, "select * from public.event_days"), "lead_id")
    inst = _group(_rows(c, "select * from public.installments"), "lead_id")
    leads = []
    for r in _rows(c, "select * from public.leads order by position"):
        k = contracts.get(r["lead_id"])
        leads.append(legacy.rebuild_lead({
            "client": clients[r["client_id"]], "lead": r, "contract": k,
            "plan": plan.get(k["contract_id"], []) if k else [], "docs": docs.get(k["contract_id"], []) if k else [],
            "days": days.get(r["lead_id"], []), "installments": inst.get(r["lead_id"], [])}))
    em = _group(_rows(c, "select * from public.alert_emails"), "alert_id")
    alerts = [legacy.rebuild_alert(r, em.get(r["alert_id"], [])) for r in _rows(c, "select * from public.alerts order by position")]
    vendors = [legacy.rebuild_flat(r, legacy.VENDOR) for r in _rows(c, "select * from public.vendors order by position")]
    lists = {"leads": leads, "alerts": alerts, "vendors": vendors}
    st = {k: v for k, v in c.run("select key, value::text from public.app_state where doc = 'tracker_data'")}
    d = {}
    for k in json.loads(st.get("_key_order", "[]")):
        d[k] = lists[k] if k in lists else json.loads(st[k])
    for k, v in lists.items():
        d.setdefault(k, v)
    return d, {}


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
    import legacy
    return _read_only(lambda c: [legacy.rebuild_flat(r, legacy.PAY) for r in _rows(c, "select * from public.payments order by position")])


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
    # Schema v2 (11/10): the write path is rebuilt for the normalized tables before cutover (Phase 4).
    # The cloud is read-only until then (api/index.py answers 403), so this must never run.
    raise RuntimeError("cloud saves are not available yet (schema v2 write path pending)")


def user_is_allowed(uid):
    """True only if this Supabase user id is on the allowlist (asks about one id; cannot list it)."""
    return bool(_read_only(lambda c: c.run("select private.user_is_allowed(cast(:u as uuid))", u=uid)[0][0]))
