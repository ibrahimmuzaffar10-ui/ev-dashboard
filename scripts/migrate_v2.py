#!/usr/bin/env python3
"""Schema v2 import: a JSON SNAPSHOT -> the normalized tables, in ONE transaction (all or nothing),
as the ev_server role. Re-runnable: it replaces everything it owns. Prints counts only.

  EV_DATA_DIR=<snapshot> .venv/bin/python scripts/migrate_v2.py
  EV_DATA_DIR=<snapshot> .venv/bin/python scripts/verify_v2.py
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import db, legacy  # noqa: E402

D = os.path.expanduser(os.environ["EV_DATA_DIR"])
def load(f):
    with open(os.path.join(D, f + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


ins = db._ins


def main():
    t, pays, ws = load("tracker_data"), load("payments"), load("watch_state")
    briefs = {f: load(f) for f in ("brief_latest", "brief_state", "brief_ack")}
    c = db._connect()
    counts = {}
    try:
        c.run("begin")
        c.run("select pg_advisory_xact_lock(:k)", k=db.LOCK_KEY)
        man = c.run("select value::text from public.app_state where doc = 'storage_manifest' and key = 'files'")
        storage = {os.path.expanduser(m["source"]): m for m in (json.loads(man[0][0]) if man else [])}
        for tbl in ("alert_emails", "alerts", "documents", "contract_plan_items", "event_days", "payments",
                    "installments", "contracts", "leads", "clients", "vendors", "emails"):
            c.run(f"delete from public.{tbl}")
        c.run("delete from public.app_state where doc <> 'storage_manifest'")

        for i, o in enumerate(t["leads"]):
            p = legacy.split_lead(o, i, storage)
            cid = ins(c, "clients", p["client"], "client_id")
            ins(c, "leads", dict(p["lead"], client_id=cid))
            kid = None
            if p["contract"]:
                kid = ins(c, "contracts", dict(p["contract"], lead_id=p["lead"]["lead_id"]), "contract_id")
                for r in p["plan"]:
                    ins(c, "contract_plan_items", dict(r, contract_id=kid))
                for r in p["docs"]:
                    ins(c, "documents", dict(r, contract_id=kid))
            for r in p["days"]:
                ins(c, "event_days", dict(r, lead_id=p["lead"]["lead_id"], contract_id=kid if r["contract_id"] is not None else None))
            for r in p["installments"]:
                ins(c, "installments", dict(r, lead_id=p["lead"]["lead_id"], contract_id=kid))
            for k in ("contract", "plan", "days", "docs", "installments"):
                counts[k] = counts.get(k, 0) + (len(p[k]) if isinstance(p[k], list) else int(bool(p[k])))
        counts["leads"] = counts["clients"] = len(t["leads"])

        for i, o in enumerate(t["alerts"]):
            row, em = legacy.split_alert(o, i)
            ins(c, "alerts", row)
            for e in em:
                ins(c, "alert_emails", dict(e, alert_id=row["alert_id"]))
            counts["alert_emails"] = counts.get("alert_emails", 0) + len(em)
        counts["alerts"] = len(t["alerts"])
        for i, o in enumerate(pays):
            ins(c, "payments", legacy.split_flat(o, i, legacy.PAY))
        counts["payments"] = len(pays)
        for i, o in enumerate(t["vendors"]):
            ins(c, "vendors", legacy.split_flat(o, i, legacy.VENDOR))
        counts["vendors"] = len(t["vendors"])

        seen = ws.get("seen", [])
        c.run("insert into public.emails (key, status) select k, 'processed' from unnest(cast(:ks as text[])) k", ks=seen)
        counts["emails"] = len(seen)
        state = [("tracker_data", "_key_order", [k for k in t if k != "changelog"])]
        state += [("tracker_data", k, v) for k, v in t.items() if k not in ("leads", "vendors", "alerts", "changelog")]
        state += [("watch_state", "_key_order", list(ws))] + [("watch_state", k, v) for k, v in ws.items() if k != "seen"]
        for f, obj in briefs.items():
            state += [(f, "_key_order", list(obj))] + [(f, k, v) for k, v in obj.items()]
        for d_, k, v in state:
            c.run("insert into public.app_state (doc, key, value) values (:d, :k, cast(:v as json))",
                  d=d_, k=k, v=json.dumps(v, ensure_ascii=False, allow_nan=False))
        counts["app_state"] = len(state)
        c.run("commit")
    except Exception:
        c.run("rollback")
        raise
    finally:
        c.close()
    print("loaded:", counts, f"(changelog {len(t.get('changelog', []))} entries not migrated)")


if __name__ == "__main__":
    main()
