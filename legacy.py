"""Schema v2 <-> the old JSON shape the current dashboard code reads. One copy of the rules,
used by the import (scripts/migrate_v2.py), the checker (scripts/verify_v2.py) and db.py.

Each old item is split into typed columns (normalized tables). `legacy_shape` records only what a
typed column cannot hold: keys that were absent, and the original value wherever the typed value
would rebuild differently ('' instead of a date, 500.0 vs 500, an unparseable date...). Rebuilding
= decode the columns, then apply legacy_shape. Lossless = the rebuilt item equals the original
(same keys, same values and types; key order ignored: Ibrahim 11/10).
"""
import datetime, json, re
from decimal import Decimal

import evtime

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
AT_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})$")
CENT = Decimal("0.01")


def canon(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False, allow_nan=False)


# ------------------------------------------------------------------ value kinds
def enc(kind, v):
    if kind == "text":
        return v if isinstance(v, str) else None
    if kind == "date":
        if isinstance(v, str) and DATE_RE.match(v):
            try:
                return datetime.date.fromisoformat(v)
            except ValueError:
                return None
        return None
    if kind in ("money_int", "money_float"):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return Decimal(repr(v)).quantize(CENT)             # same rounding as numeric(10,2)
        return None
    if kind == "bool":
        return v if isinstance(v, bool) else None
    if kind == "int":
        return v if isinstance(v, int) and not isinstance(v, bool) else None
    if kind == "at":                                          # naive Houston "YYYY-MM-DD HH:MM" -> aware
        m = AT_RE.match(v) if isinstance(v, str) else None
        if not m:
            return None
        return datetime.datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}").replace(tzinfo=evtime.CT)
    if kind == "json":
        return v
    raise ValueError(kind)


def dec(kind, v):
    if v is None:
        return None
    if kind in ("text", "bool", "int", "json"):
        return v
    if kind == "date":
        return v.isoformat()
    if kind == "money_int":
        d = Decimal(v)
        return int(d) if d == d.to_integral_value() else float(d)
    if kind == "money_float":
        return float(Decimal(v))
    if kind == "at":
        return v.astimezone(evtime.CT).strftime("%Y-%m-%d %H:%M")
    raise ValueError(kind)


def make_shape(original, rebuilt):
    absent = [k for k in rebuilt if k not in original]
    orig = {k: v for k, v in original.items() if k not in rebuilt or canon(rebuilt[k]) != canon(v)}
    s = {}
    if absent: s["absent"] = absent
    if orig: s["orig"] = orig
    return s or None


def apply_shape(rebuilt, shape):
    out = dict(rebuilt)
    for k in (shape or {}).get("absent", []):
        out.pop(k, None)
    out.update((shape or {}).get("orig", {}))
    return out


# ------------------------------------------------------------------ flat field maps: json key -> (column, kind)
CLIENT = {"client": ("name", "text"), "src_email": ("email", "text"), "alt_email": ("alt_email", "text"),
          "ig_ref": ("instagram", "text")}
LEAD = {"id": ("lead_id", "text"), "channel": ("channel", "text"), "service": ("service", "text"),
        "source": ("source", "text"), "inquiry": ("inquiry_on", "date"), "last_contact": ("last_contact_on", "date"),
        "event_text": ("event_text", "text"), "venue": ("venue", "text"), "status": ("status", "text"),
        "replied": ("replied", "text"), "contract": ("contract_status", "text"), "retainer": ("retainer_status", "text"),
        "balance": ("balance_status", "text"), "gallery": ("gallery", "text"), "review": ("review", "text"),
        "lost_reason": ("lost_reason", "text"), "fault": ("fault", "text"), "price_obj": ("price_objection", "bool"),
        "quote": ("quote", "text"), "total": ("total", "money_int"), "paid": ("paid_manual", "money_int"),
        "notes": ("notes", "text"), "action_note": ("action_note", "text")}
CONTRACT = {"name": ("name", "text"), "issue": ("issued_on", "date"), "sign_by": ("sign_by", "date"),
            "signed_on": ("signed_on", "date"), "total": ("total", "money_int"), "retainer": ("retainer", "money_int"),
            "fields": ("fields", "json")}
PLAN = {"label": ("label", "text"), "due": ("due_on", "date"), "amount": ("amount", "money_int")}
DAY = {"event": ("label", "text"), "date": ("day", "date"), "start": ("start_local", "text"),
       "end": ("end_local", "text"), "hours": ("hours", "text")}
INST = {"label": ("label", "text"), "due": ("due_on", "date"), "amount": ("amount", "money_int"),
        "paid": ("paid", "bool"), "paid_on": ("paid_on", "date")}
PAY = {"email_id": ("email_id", "text"), "date": ("received_on", "date"), "amount": ("amount", "money_float"),
       "sender": ("sender", "text"), "memo": ("memo", "text"), "method": ("method", "text"),
       "lead_id": ("lead_id", "text"), "client": ("client_label", "text")}
ALERT = {"id": ("alert_id", "text"), "at": ("at", "at"), "type": ("type", "text"), "title": ("title", "text"),
         "detail": ("detail", "text"), "from_email": ("from_email", "text"), "lead_id": ("lead_id", "text"),
         "done": ("done", "bool"), "done_at": ("done_on", "date"), "unread": ("unread", "bool"),
         "ignored": ("ignored", "bool"), "awaiting_reply": ("awaiting_reply", "bool"),
         "clarify_sent": ("clarify_sent_on", "date"), "count": ("count", "int")}
VENDOR = {k: (k, "text") for k in ("name", "channel", "type", "note", "follow")}
DOC_KEYS = (("draft_files", "draft", True), ("questionnaire_files", "questionnaire", True), ("signed_file", "signed", False))


def enc_flat(o, spec):
    return {col: enc(kind, o.get(k)) for k, (col, kind) in spec.items()}


def dec_flat(row, spec):
    return {k: dec(kind, row.get(col)) for k, (col, kind) in spec.items()}


def flat_item(o, spec):
    """Encode one flat item and attach its legacy_shape (rebuild must equal o)."""
    row = enc_flat(o, spec)
    row["legacy_shape"] = make_shape(o, dec_flat(row, spec))
    return row


def rebuild_flat(row, spec):
    return apply_shape(dec_flat(row, spec), row.get("legacy_shape"))


# ------------------------------------------------------------------ leads (client + lead + contract + days + plan + docs + installments)
def rebuild_lead(p):
    """p = {client, lead, contract|None, plan[], days[], docs[], installments[]} (rows as read from the DB)."""
    d = dec_flat(p["client"], CLIENT)
    d.update(dec_flat(p["lead"], LEAD))
    days = sorted(p["days"], key=lambda r: r["position"])
    d["event"] = days[0]["day"].isoformat() if days and days[0]["day"] else None
    if p["installments"]:
        d["schedule"] = [rebuild_flat(r, INST) for r in sorted(p["installments"], key=lambda r: r["position"])]
    c = p["contract"]
    if c:
        ct = dec_flat(c, CONTRACT)
        ct["days"] = [rebuild_flat(r, DAY) for r in days if r.get("contract_id") is not None]
        ct["plan"] = [rebuild_flat(r, PLAN) for r in sorted(p["plan"], key=lambda r: r["position"])]
        for key, kind, many in DOC_KEYS:
            files = [r["original_path"] for r in sorted(p["docs"], key=lambda r: r["position"]) if r["kind"] == kind]
            if files:
                ct[key] = files if many else files[0]
        d["contract_terms"] = apply_shape(ct, c.get("legacy_shape"))
    return apply_shape(d, p["lead"].get("legacy_shape"))


def split_lead(o, position, storage=None):
    """One old lead -> rows for every table, with legacy_shapes so rebuild_lead(rows) == o."""
    storage = storage or {}
    ct = o.get("contract_terms") if isinstance(o.get("contract_terms"), dict) else None
    p = {"client": enc_flat(o, CLIENT), "lead": enc_flat(o, LEAD), "contract": None, "plan": [], "days": [], "docs": [],
         "installments": []}
    p["lead"]["position"] = position
    if ct:
        c = enc_flat(ct, CONTRACT)
        p["contract"] = c
        p["plan"] = [dict(flat_item(x, PLAN), position=i) for i, x in enumerate(ct.get("plan") or []) if isinstance(x, dict)]
        p["days"] = [dict(flat_item(x, DAY), position=i, contract_id=0, venue=None) for i, x in enumerate(ct.get("days") or [])
                     if isinstance(x, dict)]
        for key, kind, many in DOC_KEYS:
            v = ct.get(key)
            files = v if (many and isinstance(v, list)) else ([v] if (not many and isinstance(v, str)) else [])
            for i, f in enumerate(files):
                if isinstance(f, str):
                    s = storage.get(f) or {}
                    p["docs"].append({"kind": kind, "position": i, "original_path": f,
                                      "storage_key": s.get("key"), "sha256": s.get("sha256")})
        ct_rebuilt = rebuild_lead(dict(p, lead={**p["lead"], "legacy_shape": None}))["contract_terms"]
        c["legacy_shape"] = make_shape(ct, ct_rebuilt)
    if not p["days"]:
        ev = enc("date", o.get("event"))
        if ev:
            p["days"] = [{"position": 0, "contract_id": None, "label": None, "day": ev, "start_local": None,
                          "end_local": None, "hours": None, "venue": None, "legacy_shape": None}]
    for i, x in enumerate(o.get("schedule") or [] if isinstance(o.get("schedule"), list) else []):
        if isinstance(x, dict):
            p["installments"].append(dict(flat_item(x, INST), position=i))
    p["lead"]["legacy_shape"] = None
    p["lead"]["legacy_shape"] = make_shape(o, rebuild_lead(p))
    return p


# ------------------------------------------------------------------ alerts (alert + alert_emails)
def split_alert(o, position):
    row = enc_flat(o, ALERT)
    row["position"] = position
    emails = [o.get("email_id")] + (list(o["email_ids"]) if isinstance(o.get("email_ids"), list) else [])
    em = [{"position": i, "email_key": e if isinstance(e, str) else None} for i, e in enumerate(emails)]
    row["legacy_shape"] = None
    row["legacy_shape"] = make_shape(o, rebuild_alert(row, em))
    return row, em


def rebuild_alert(row, emails):
    d = dec_flat(row, ALERT)
    em = [e["email_key"] for e in sorted(emails, key=lambda e: e["position"])]
    d["email_id"] = em[0] if em else None
    if len(em) > 1:
        d["email_ids"] = em[1:]
    return apply_shape(d, row.get("legacy_shape"))


def split_flat(o, position, spec):
    return dict(flat_item(o, spec), position=position)
