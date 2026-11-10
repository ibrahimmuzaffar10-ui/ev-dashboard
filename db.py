"""Data layer for server.py. (Supabase reads use schema v2 since 11/10; see legacy.py.)

EV_BACKEND=json      (default) today's JSON files, unchanged.
EV_BACKEND=supabase  Postgres via the Supabase pooler, as the `ev_server` role.

Save path (supabase):  with db.locked(LOCK): d = load(); <route code>; store(d)
  * locked() opens ONE transaction and takes a transaction-level advisory lock, so saves from
    every server instance (Mac, Vercel) run one at a time, like the old threading.Lock.
  * store() compares every lead/alert with what load() read and rewrites only what changed, in
    the normalized tables (schema v2, via legacy.py), incl. deletes (alert folding); then it
    COMMITS, before the route sends its 200. A failed commit = an error, never a false success.
    No changelog (dropped 11/10).
  * No session state is used (no prepared statements, no session locks): safe on the
    transaction pooler (port 6543).
"""
import json, os, ssl, threading, time

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
        # Connecting or queueing can fail transiently under load; nothing is written yet, so one
        # retry is safe. Any error after this point is returned to the caller, never swallowed.
        for attempt in (1, 2):
            c = None
            try:
                c = _connect()
                c.run("begin")
                c.run("select pg_advisory_xact_lock(:k)", k=LOCK_KEY)
                break
            except Exception:
                if c is not None:
                    try: c.close()
                    except Exception: pass
                if attempt == 2:
                    raise
                time.sleep(0.5)
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


# One round trip for the whole dataset (saves queue on one lock, so load time matters).
# Ordered lists come back in position order; json values (app_state) stay text so they rebuild exactly.
_ALL = ("select json_build_object("
        "'clients', (select coalesce(json_agg(t), '[]') from public.clients t),"
        "'leads', (select coalesce(json_agg(t order by t.position), '[]') from public.leads t),"
        "'contracts', (select coalesce(json_agg(t), '[]') from public.contracts t),"
        "'contract_plan_items', (select coalesce(json_agg(t), '[]') from public.contract_plan_items t),"
        "'documents', (select coalesce(json_agg(t), '[]') from public.documents t),"
        "'event_days', (select coalesce(json_agg(t), '[]') from public.event_days t),"
        "'installments', (select coalesce(json_agg(t), '[]') from public.installments t),"
        "'alerts', (select coalesce(json_agg(t order by t.position), '[]') from public.alerts t),"
        "'alert_emails', (select coalesce(json_agg(t), '[]') from public.alert_emails t),"
        "'vendors', (select coalesce(json_agg(t order by t.position), '[]') from public.vendors t),"
        "'app_state', (select coalesce(json_agg(json_build_object('key', key, 'value', value::text)), '[]') "
        "              from public.app_state where doc = 'tracker_data'))::text")


def _fetch_all(c):
    return json.loads(c.run(_ALL)[0][0])


def _read(c):
    """Schema v2 (normalized) -> the old tracker_data shape the route code expects (see legacy.py)."""
    import legacy
    T = _fetch_all(c)
    clients = {r["client_id"]: r for r in T["clients"]}
    contracts = {r["lead_id"]: r for r in T["contracts"]}
    plan = _group(T["contract_plan_items"], "contract_id")
    docs = _group(T["documents"], "contract_id")
    days = _group(T["event_days"], "lead_id")
    inst = _group(T["installments"], "lead_id")
    leads = []
    lead_rows = T["leads"]
    for r in lead_rows:
        k = contracts.get(r["lead_id"])
        leads.append(legacy.rebuild_lead({
            "client": clients[r["client_id"]], "lead": r, "contract": k,
            "plan": plan.get(k["contract_id"], []) if k else [], "docs": docs.get(k["contract_id"], []) if k else [],
            "days": days.get(r["lead_id"], []), "installments": inst.get(r["lead_id"], [])}))
    em = _group(T["alert_emails"], "alert_id")
    alert_rows = T["alerts"]
    alerts = [legacy.rebuild_alert(r, em.get(r["alert_id"], [])) for r in alert_rows]
    vendors = [legacy.rebuild_flat(r, legacy.VENDOR) for r in T["vendors"]]
    lists = {"leads": leads, "alerts": alerts, "vendors": vendors}
    st = {r["key"]: r["value"] for r in T["app_state"]}
    d = {}
    for k in json.loads(st.get("_key_order", "[]")):
        d[k] = lists[k] if k in lists else json.loads(st[k])
    for k, v in lists.items():
        d.setdefault(k, v)
    # what store() needs to write only what changed
    snap = {"lead": {r["lead_id"]: (r["position"], legacy.canon(o)) for r, o in zip(lead_rows, leads)},
            "client_id": {r["lead_id"]: r["client_id"] for r in lead_rows},
            "contract_id": {k: v["contract_id"] for k, v in contracts.items()},
            "alert": {r["alert_id"]: (r["position"], legacy.canon(o)) for r, o in zip(alert_rows, alerts)},
            "vendors": [legacy.canon(v) for v in vendors], "app": st}
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
        return {k: json.loads(st[k]) for k in json.loads(st["_key_order"]) if k in st}
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
JSONB = {"legacy_shape", "fields"}


def _params(row):
    return {k: (None if v is None else json.dumps(v, ensure_ascii=False, allow_nan=False)) if k in JSONB else v
            for k, v in row.items()}


def _ins(c, table, row, returning=None):
    cols = list(row)
    vals = ", ".join(f"cast(:{k} as jsonb)" if k in JSONB else f":{k}" for k in cols)
    out = c.run(f"insert into public.{table} ({', '.join(cols)}) values ({vals})"
                + (f" returning {returning}" if returning else ""), **_params(row))
    return out[0][0] if returning else None


def _upd(c, table, row, key, val):
    sets = ", ".join(f"{k} = cast(:{k} as jsonb)" if k in JSONB else f"{k} = :{k}" for k in row)
    c.run(f"update public.{table} set {sets} where {key} = :__key", __key=val, **_params(row))


def _storage(c):
    man = c.run("select value::text from public.app_state where doc = 'storage_manifest' and key = 'files'")
    return {os.path.expanduser(m["source"]): m for m in (json.loads(man[0][0]) if man else [])}


def _write_lead(c, snap, o, pos, storage):
    import legacy
    p = legacy.split_lead(o, pos, storage)
    lid = p["lead"]["lead_id"]
    if not lid:
        raise ValueError("lead without id")
    cid = snap["client_id"].get(lid)
    if cid:
        _upd(c, "clients", p["client"], "client_id", cid)
    else:
        cid = _ins(c, "clients", p["client"], "client_id")
        snap["client_id"][lid] = cid
    row = dict(p["lead"], client_id=cid)
    if lid in snap["lead"]:
        _upd(c, "leads", row, "lead_id", lid)
    else:
        _ins(c, "leads", row)
    c.run("delete from public.event_days where lead_id = :l", l=lid)
    c.run("delete from public.installments where lead_id = :l", l=lid)
    kid = snap["contract_id"].get(lid)
    if p["contract"]:
        crow = dict(p["contract"], lead_id=lid)
        if kid:
            _upd(c, "contracts", crow, "contract_id", kid)
            c.run("delete from public.contract_plan_items where contract_id = :k", k=kid)
            c.run("delete from public.documents where contract_id = :k", k=kid)
        else:
            kid = _ins(c, "contracts", crow, "contract_id")
            snap["contract_id"][lid] = kid
        for r in p["plan"]:
            _ins(c, "contract_plan_items", dict(r, contract_id=kid))
        for r in p["docs"]:
            _ins(c, "documents", dict(r, contract_id=kid))
    elif kid:
        c.run("delete from public.contracts where contract_id = :k", k=kid)
        snap["contract_id"].pop(lid, None)
        kid = None
    for r in p["days"]:
        _ins(c, "event_days", dict(r, lead_id=lid, contract_id=kid if r["contract_id"] is not None else None))
    for r in p["installments"]:
        _ins(c, "installments", dict(r, lead_id=lid, contract_id=kid))


def _delete_lead(c, snap, lid):
    c.run("delete from public.event_days where lead_id = :l", l=lid)
    c.run("delete from public.installments where lead_id = :l", l=lid)
    c.run("delete from public.contracts where lead_id = :l", l=lid)
    c.run("delete from public.leads where lead_id = :l", l=lid)
    c.run("delete from public.clients where client_id = :c and not exists "
          "(select 1 from public.leads where client_id = :c)", c=snap["client_id"].get(lid))


def store(d):
    """Write exactly what changed since load(), across the normalized tables, then COMMIT."""
    import legacy
    tx = getattr(_tls, "tx", None)
    if not tx or tx["snap"] is None:
        raise RuntimeError("store() outside a locked load()")
    if tx["done"]:
        raise RuntimeError("store() called twice in one request")
    c, snap = tx["conn"], tx["snap"]
    storage = None

    leads = d.get("leads", [])
    ids = [o.get("id") for o in leads]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate lead id")
    for lid in [x for x in snap["lead"] if x not in set(ids)]:
        _delete_lead(c, snap, lid)
    for i, o in enumerate(leads):
        old = snap["lead"].get(o.get("id"))
        cur = legacy.canon(o)
        if old and old[1] == cur:
            if old[0] != i:
                c.run("update public.leads set position = :p where lead_id = :l", p=i, l=o["id"])
            continue
        if storage is None:
            storage = _storage(c)
        _write_lead(c, snap, o, i, storage)

    alerts = d.get("alerts", [])
    aids = [a.get("id") for a in alerts]
    if len(aids) != len(set(aids)):
        raise ValueError("duplicate alert id")
    gone = [x for x in snap["alert"] if x not in set(aids)]
    if gone:
        c.run("delete from public.alerts where alert_id = any(cast(:ids as text[]))", ids=gone)
    for i, o in enumerate(alerts):
        old = snap["alert"].get(o.get("id"))
        if old and old[1] == legacy.canon(o):
            if old[0] != i:
                c.run("update public.alerts set position = :p where alert_id = :a", p=i, a=o["id"])
            continue
        row, em = legacy.split_alert(o, i)
        if old:
            _upd(c, "alerts", row, "alert_id", row["alert_id"])
            c.run("delete from public.alert_emails where alert_id = :a", a=row["alert_id"])
        else:
            _ins(c, "alerts", row)
        for e in em:
            _ins(c, "alert_emails", dict(e, alert_id=row["alert_id"]))

    vendors = d.get("vendors", [])
    if [legacy.canon(v) for v in vendors] != snap["vendors"]:
        c.run("delete from public.vendors")
        for i, v in enumerate(vendors):
            _ins(c, "vendors", legacy.split_flat(v, i, legacy.VENDOR))

    order = [k for k in d if k != "changelog"]
    want = {k: j(d[k]) for k in order if k not in ("leads", "alerts", "vendors")}
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


# ------------------------------------------------------------------ Mac jobs (watcher, Zelle import, brief)
# Same calls in both modes: JSON files in EV_DATA_DIR, or Supabase.
DATA_DIR = os.path.expanduser(os.environ.get("EV_DATA_DIR", HERE))


def doc_read(name):
    """A small state file (watch_state, brief_state, brief_latest, zelle_ids ...) or None."""
    if CLOUD:
        return read_doc(name)
    p = os.path.join(DATA_DIR, name + ".json")
    return json.load(open(p)) if os.path.exists(p) else None


def doc_write(name, obj, **dump):
    if CLOUD:
        return write_doc(name, obj)
    tmp = os.path.join(DATA_DIR, f".{name}.json.tmp")
    with open(tmp, "w") as f:
        json.dump(obj, f, **dump)
    os.replace(tmp, os.path.join(DATA_DIR, name + ".json"))      # never a half-written file


def payments_all():
    if CLOUD:
        return payments()
    p = os.path.join(DATA_DIR, "payments.json")
    return json.load(open(p)) if os.path.exists(p) else []


def payments_save(pays):
    """Replace the payments list: only changed rows are written, under the save lock."""
    if not CLOUD:
        return doc_write("payments", pays, indent=1)
    import legacy
    with locked(None):
        c = _tls.tx["conn"]
        have = {}
        for r in json.loads(c.run("select coalesce(json_agg(t), '[]')::text from public.payments t")[0][0]):
            have[r["email_id"]] = (r["position"], legacy.canon(legacy.rebuild_flat(r, legacy.PAY)))
        keys = [p.get("email_id") for p in pays]
        if len(keys) != len(set(keys)) or None in keys:
            raise ValueError("payments need unique email_id")
        gone = [k for k in have if k not in set(keys)]
        if gone:
            c.run("delete from public.payments where email_id = any(cast(:k as text[]))", k=gone)
        for i, p in enumerate(pays):
            old = have.get(p["email_id"])
            if old and old[1] == legacy.canon(p):
                if old[0] != i:
                    c.run("update public.payments set position = :i where email_id = :e", i=i, e=p["email_id"])
                continue
            row = legacy.split_flat(p, i, legacy.PAY)
            if old:
                _upd(c, "payments", row, "email_id", p["email_id"])
            else:
                _ins(c, "payments", row)
        c.run("commit")
        _tls.tx["done"] = True


def email_rows():
    """{key: (status, attempts)} for every email the watcher has looked at (cloud)."""
    return {k: (s, a) for k, s, a in _read_only(lambda c: c.run("select key, status, attempts from public.emails"))}


def emails_upsert(rows):
    """rows: [(key, folder, status, attempts)] -> emails table, one transaction."""
    if not rows:
        return
    c = _connect()
    try:
        c.run("begin")
        for key, folder, status, attempts in rows:
            c.run("insert into public.emails (key, folder, status, attempts) values (:k, :f, :s, :a) "
                  "on conflict (key) do update set folder = coalesce(excluded.folder, public.emails.folder), "
                  "status = excluded.status, attempts = excluded.attempts", k=key, f=folder, s=status, a=attempts)
        c.run("commit")
    finally:
        c.close()


# ------------------------------------------------------------------ email outbox (step 3)
def outbox_enqueue(to, subject, body, in_reply_to=None, files=()):
    """Queue an email. Inside a save (locked, not yet stored) it joins that transaction, so it is
    queued only if the save commits. Otherwise (after the save) it gets its own transaction."""
    import hashlib, mailer
    mid = mailer.new_message_id()
    tx = getattr(_tls, "tx", None)
    own = not (tx and not tx["done"])
    c = _connect() if own else tx["conn"]
    try:
        if own:
            c.run("begin")
        oid = c.run("insert into public.outbox (message_id, to_addr, subject, body, in_reply_to) "
                    "values (:m, :t, :s, :b, :r) returning outbox_id", m=mid, t=to, s=subject, b=body, r=in_reply_to)[0][0]
        for i, (name, ctype, data) in enumerate(files or ()):
            c.run("insert into public.outbox_files (outbox_id, position, filename, content_type, data, sha256) "
                  "values (:o, :p, :n, :c, :d, :h)", o=oid, p=i, n=name, c=ctype, d=data, h=hashlib.sha256(data).hexdigest())
        if own:
            c.run("commit")
    except Exception:
        if own:
            c.run("rollback")
        raise
    finally:
        if own:
            c.close()
    return mid


def user_is_allowed(uid):
    """True only if this Supabase user id is on the allowlist (asks about one id; cannot list it)."""
    return bool(_read_only(lambda c: c.run("select private.user_is_allowed(cast(:u as uuid))", u=uid)[0][0]))
