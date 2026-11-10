#!/usr/bin/env python3
"""Phase 3: JSON files -> Supabase tables. One transaction, re-runnable (it replaces what it owns).

Reads a SNAPSHOT of the data folder (never the live one: the watcher writes every 5 min) and writes
one SQL file. That SQL file holds client data: put it in a scratch folder and delete it after.
Prints counts only, never a value.

  EV_DATA_DIR=<snapshot> python3 scripts/migrate_data.py <out.sql>
  supabase db query --linked -f <out.sql>
  EV_DATA_DIR=<snapshot> python3 scripts/verify_migration.py

Exactness: each item is sent as JSON text and stored in a `json` column, which keeps the text
verbatim (key order, missing-vs-null, 500 vs 500.0). verify_migration.py proves it byte for byte.
"""
import json, os, secrets, sys

D = os.path.expanduser(os.environ["EV_DATA_DIR"])
FILES = ("tracker_data", "payments", "watch_state", "brief_latest", "brief_state", "brief_ack")
TABLE_LISTS = ("leads", "vendors", "alerts")      # tracker_data keys that get their own table
DROPPED = {"changelog"}                            # not migrated (Ibrahim 11/10)
TAG = "ev" + secrets.token_hex(8)                  # dollar-quote tag that cannot occur in the data


def j(v):
    return json.dumps(v, ensure_ascii=False, allow_nan=False)


def lit(s):
    if f"${TAG}$" in s or "\x00" in s:
        sys.exit("refusing: value contains the quote tag or a NUL")
    return f"${TAG}${s}${TAG}$"


def main(out):
    data = {}
    for f in FILES:
        with open(os.path.join(D, f + ".json"), encoding="utf-8") as fh:
            data[f] = json.load(fh)                # fails loudly on a half-written file
    t, pays, ws = data["tracker_data"], data["payments"], data["watch_state"]
    assert isinstance(t, dict) and isinstance(pays, list) and isinstance(ws, dict)
    for k in TABLE_LISTS:
        assert isinstance(t.get(k), list), f"tracker_data.{k} missing or not a list"

    sql = ["begin;",
           "delete from public.leads; delete from public.alerts; delete from public.vendors;",
           "delete from public.payments; delete from public.emails;",
           "delete from public.app_state where doc <> 'storage_manifest';"]  # migrate_files.py owns that one
    counts = {}

    def items(table, lst):
        counts[table] = len(lst)
        if lst:
            rows = ",\n".join(f"({i}, {lit(j(o))}::json)" for i, o in enumerate(lst))
            sql.append(f"insert into public.{table} (pos, raw) values\n{rows};")

    for k in TABLE_LISTS:
        items(k, t[k])
    items("payments", pays)

    seen = ws.get("seen", [])
    assert all(isinstance(x, str) for x in seen) and len(seen) == len(set(seen))
    counts["emails"] = len(seen)
    if seen:
        sql.append("insert into public.emails (key, status) values\n"
                   + ",\n".join(f"({lit(x)}, 'processed')" for x in seen) + ";")

    state = []                                      # (doc, key, value)
    def doc(name, obj, exclude):
        if isinstance(obj, dict):
            state.append((name, "_key_order", [k for k in obj if k not in DROPPED]))
            state.extend((name, k, v) for k, v in obj.items() if k not in exclude)
        else:
            state.append((name, "", obj))
    doc("tracker_data", t, set(TABLE_LISTS) | DROPPED)
    doc("watch_state", ws, {"seen"})
    for f in ("brief_latest", "brief_state", "brief_ack"):
        doc(f, data[f], set())
    counts["app_state"] = len(state)
    sql.append("insert into public.app_state (doc, key, value) values\n"
               + ",\n".join(f"({lit(d)}, {lit(k)}, {lit(j(v))}::json)" for d, k, v in state) + ";")
    sql.append("commit;")

    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("\n".join(sql) + "\n")
    print("rows to load:", counts, f"(changelog {len(t.get('changelog', []))} entries skipped)")


if __name__ == "__main__":
    main(sys.argv[1])
