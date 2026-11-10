"""JSON object <-> table row, lossless (schema v1). Stdlib only.

Used by the Phase 3 migration and the Phase 4 data layer. Rules (see the migration header):
  * key_order lists the object's keys in order; a column whose key isn't listed was MISSING.
  * a key with no column, or a value whose JSON type doesn't fit its column, goes in `extra`.
  * money columns are numeric. encode() hands them over as Decimal(repr(v)) so 500.0 is stored as
    '500.0' (numeric keeps the scale) and 500 as '500'; decode() turns a Decimal with decimals back
    into float, otherwise int. Pass the Decimal to Postgres as-is (never via float8, which drops it).
"""
from decimal import Decimal

TEXT, NUM, INT, BOOL, JSON = "text", "num", "int", "bool", "json"

_LEAD_TEXT = ("client channel service inquiry event event_text venue replied status quote contract retainer balance "
              "gallery review lost_reason fault source notes src_email alt_email ig_ref action_note last_contact").split()
COLUMNS = {
    "leads": {"id": TEXT, **{k: TEXT for k in _LEAD_TEXT}, "total": NUM, "paid": NUM, "price_obj": BOOL,
              "contract_terms": JSON, "schedule": JSON},
    "alerts": {"id": TEXT, "at": TEXT, "type": TEXT, "title": TEXT, "detail": TEXT, "email_id": TEXT, "email_ids": JSON,
               "from_email": TEXT, "lead_id": TEXT, "done": BOOL, "done_at": TEXT, "unread": BOOL, "ignored": BOOL,
               "count": INT, "clarify_sent": TEXT, "awaiting_reply": BOOL},
    "vendors": {"name": TEXT, "type": TEXT, "channel": TEXT, "note": TEXT},
    "payments": {"email_id": TEXT, "date": TEXT, "amount": NUM, "sender": TEXT, "memo": TEXT, "method": TEXT,
                 "lead_id": TEXT, "client": TEXT},
    "changelog": {"at": TEXT, "by": TEXT, "client": TEXT, "field": TEXT, "id": TEXT, "old": JSON, "new": JSON},
}
# columns that are NOT NULL with a default in SQL: a JSON null can't be stored there, so it goes to extra
NOT_NULL = {("alerts", "email_ids"), ("alerts", "count")}


def _fits(kind, v):
    if kind == JSON: return True
    if v is None: return True
    if kind == TEXT: return isinstance(v, str)
    if kind == BOOL: return isinstance(v, bool)
    if kind == INT: return isinstance(v, int) and not isinstance(v, bool)
    # exponent floats (1e+20) don't survive the Decimal round trip -> extra
    if kind == NUM: return (isinstance(v, int) or (isinstance(v, float) and "e" not in repr(v) and v == v)) and not isinstance(v, bool)
    return False


def encode(table, obj, pos):
    """JSON object -> row dict (column -> value). JSON-kind columns hold Python values; the
    caller wraps them for jsonb. For changelog old/new, a missing key is SQL NULL (key_order
    tells), and JSON null is stored as jsonb 'null'."""
    cols = COLUMNS[table]
    row = {k: None for k in cols}
    row.update(pos=pos, extra={}, key_order=list(obj.keys()))
    for k, v in obj.items():
        kind = cols.get(k)
        if kind is None or not _fits(kind, v) or (v is None and (table, k) in NOT_NULL):
            row["extra"][k] = v
        elif kind == NUM and v is not None:
            row[k] = Decimal(repr(v))
        else:
            row[k] = v
    return row


def _num(v):
    if isinstance(v, Decimal):
        return float(v) if v.as_tuple().exponent < 0 else int(v)
    return v


def decode(table, row):
    """Row dict -> JSON object with the original keys, order, nulls and number types."""
    cols, extra = COLUMNS[table], row.get("extra") or {}
    order = row.get("key_order")
    if order is None:  # row written outside the Python layer: every non-null column, then extra
        order = [k for k in cols if row.get(k) is not None] + [k for k in extra if k not in cols]
    out = {}
    for k in order:
        if k in extra:
            out[k] = extra[k]
        else:
            v = row.get(k)
            out[k] = _num(v) if cols.get(k) in (NUM, INT) else v
    return out
