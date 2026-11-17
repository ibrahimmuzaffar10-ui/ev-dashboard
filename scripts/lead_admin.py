#!/usr/bin/env python3
"""Delete one lead safely (cloud). Built so routine clean-ups (TEST leads, duplicates) need no hand-written SQL.

  .venv/bin/python scripts/lead_admin.py show   <lead id>
  .venv/bin/python scripts/lead_admin.py delete <lead id> --name "<exact client name>" [--yes]

Safety: the id AND the exact client name must match (a typo in the id can't hit another client);
without --yes it is a dry run; a lead with a signed contract or payments is refused (that is
business history, not a clean-up); before deleting, the full record (lead + its alerts' links +
its registered files) is copied to Application Support/emanant-hq/deleted-leads/ (private, never in
git). The lead's files in the database are removed with it; alerts pointing at it are unlinked, not
deleted. Runs under the same lock as the dashboard's saves. Prints ids/counts only."""
import argparse, json, os, sys, threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["EV_BACKEND"] = "supabase"
import evenv, evtime, db  # noqa: E402

KEEP = os.path.expanduser("~/Library/Application Support/emanant-hq/deleted-leads")


def lead_files(lead):
    t = lead.get("contract_terms") or {}
    paths = list(t.get("draft_files") or []) + [x for x in (t.get("signed_file"), t.get("questionnaire_file")) if x]
    paths += list(t.get("questionnaire_files") or [])
    return [p for p in paths if isinstance(p, str)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["show", "delete"])
    ap.add_argument("lead_id")
    ap.add_argument("--name", default=None)
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()

    with db.locked(threading.Lock()):
        d = db.load()
        hits = [l for l in d["leads"] if l.get("id") == a.lead_id]
        if len(hits) != 1:
            sys.exit(f"{a.lead_id}: not found")
        lead = hits[0]
        pays = [p for p in db.payments_all() if p.get("lead_id") == a.lead_id] if hasattr(db, "payments_all") else []
        alerts = [x for x in d.get("alerts", []) if x.get("lead_id") == a.lead_id]
        files = lead_files(lead)
        print(f"{a.lead_id}: status={lead.get('status')} contract={lead.get('contract')} payments={len(pays)} "
              f"linked alerts={len(alerts)} files={len(files)}")
        if a.action == "show":
            return
        if a.name is None or a.name != lead.get("client"):
            sys.exit("refused: --name must be the lead's exact client name")
        if lead.get("contract") == "signed" or pays:
            sys.exit("refused: signed contract or payments on this lead (business history); do it by hand with Ibrahim")
        if not a.yes:
            print("dry run: nothing changed (add --yes to delete)")
            return
        os.makedirs(KEEP, mode=0o700, exist_ok=True)
        stamp = evtime.now_ct().strftime("%Y%m%d-%H%M%S")
        reg = db.file_registry()
        keep = {"deleted_at": evtime.now_ct().isoformat(timespec="seconds"), "lead": lead,
                "alert_ids_unlinked": [x.get("id") for x in alerts],
                "files": [m for m in reg if m.get("source") in files]}
        path = os.path.join(KEEP, f"{a.lead_id}-{stamp}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(keep, fh, ensure_ascii=False, indent=1)
        os.chmod(path, 0o600)
        for x in alerts:
            x.pop("lead_id", None)
        n0 = len(d["leads"])
        d["leads"] = [l for l in d["leads"] if l.get("id") != a.lead_id]
        db.store(d)

    # files belong to this lead only (their names carry the lead's client name)
    gone = [m for m in reg if m.get("source") in files]
    if gone:
        c = db._connect()
        try:
            c.run("begin")
            c.run("delete from public.files where file_key = any(cast(:k as text[]))", k=[m["key"] for m in gone if m.get("key")])
            # re-read under a row lock (same as db.file_put) so a file saved meanwhile is never dropped
            got = c.run("select value::text from public.app_state where doc = 'storage_manifest' and key = 'files' for update")
            rest = [m for m in (json.loads(got[0][0]) if got else []) if m.get("source") not in files]
            c.run("update public.app_state set value = cast(:v as json) where doc = 'storage_manifest' and key = 'files'",
                  v=json.dumps(rest, ensure_ascii=False))
            c.run("commit")
        finally:
            c.close()
    left = db.load()
    ok = len(left["leads"]) == n0 - 1 and not any(l.get("id") == a.lead_id for l in left["leads"])
    print(f"{'deleted' if ok else 'FAILED to delete'} {a.lead_id}; files removed {len(gone)}; alerts unlinked {len(alerts)}; "
          f"copy kept in Application Support/emanant-hq/deleted-leads/")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
