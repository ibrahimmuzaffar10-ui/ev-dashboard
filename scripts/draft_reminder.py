"""Write a client reminder as a DRAFT in Eman's Mail (Drafts folder): nothing is sent; she reviews and taps Send.

    .venv/bin/python scripts/draft_reminder.py L000 deposit   [--dry-run]   # signed, deposit not in yet
    .venv/bin/python scripts/draft_reminder.py L000 sign      [--dry-run]   # contract sent, not signed yet

Same voice as the approved contract email (send_contract.py). Hormozi: one clear next step, the real deadline, no
pressure tricks. Run with EV_BACKEND=supabase.
"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evenv, db, evtime, mailer  # noqa: E402,F401
from send_contract import nice_date, money  # noqa: E402


def reminder(lead, kind, this_year):
    t = lead["contract_terms"]; f = t["fields"]
    words = [w for w in (f.get("first_names") or f.get("client_names") or "").replace("&", " ").split()
             if w.rstrip(".").lower() not in ("dr", "mr", "mrs", "ms", "miss")]
    first = words[0] if words else "there"
    event = (f.get("session_type") or "event").strip().lower()
    day = t["days"][0]["date"]; when = nice_date(day, True, this_year)
    to = (f.get("client_email") or lead.get("src_email") or "").strip()
    if kind == "deposit":
        dep = next((s for s in lead.get("schedule") or [] if not s.get("paid") and "retainer" in str(s.get("label", "")).lower()), None)
        if not dep: sys.exit(f"{lead['id']}: no unpaid deposit on the plan")
        rest = [s for s in lead["schedule"] if not s.get("paid") and s is not dep]
        rest_line = (f"The remaining {money(sum(float(s['amount']) for s in rest))} is due on or before "
                     f"{nice_date(max(s['due'] for s in rest), False, this_year)}.\n\n") if rest else ""
        subject = f"Your deposit for your {event} on {nice_date(day, False, this_year)}"
        body = (f"Hi {first},\n\nThank you so much for signing your contract! We're so excited for your {event} on {when}.\n\n"
                f"Just a quick reminder that the {money(dep['amount'])} deposit is what officially holds your date. Whenever you get "
                f"a chance, you can send it by Zelle (the details are in your contract); please put your name and the event date in the memo.\n\n"
                f"{rest_line}If you have any questions at all, just reply to this email.\n\nSee you soon!\n\nEman\nEmanant Visuals\n")
    else:
        link = t.get("docuseal_link")
        if not link: sys.exit(f"{lead['id']}: no signing link on the contract")
        sign_by = nice_date(t["sign_by"], False, this_year)
        dep = (money(t["retainer"]) + " ") if t.get("retainer") else ""
        subject = f"Friendly reminder: your Emanant Visuals contract (sign by {sign_by})"
        body = (f"Hi {first},\n\nJust a friendly reminder that your contract for your {event} on {when} is ready to sign here:\n\n{link}\n\n"
                f"The link is valid until {sign_by}. Your date is reserved once the contract is signed and the {dep}deposit is received "
                f"(Zelle details are in the contract).\n\nIf anything needs changing or you have any questions, just reply to this email "
                f"and I'll take care of it.\n\nWe're so excited to work with you!\n\nEman\nEmanant Visuals\n")
    return to, subject, body


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("lead_id"); ap.add_argument("kind", choices=["deposit", "sign"]); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    lead = next((l for l in db.load()["leads"] if l.get("id") == a.lead_id), None)
    if not lead or not lead.get("contract_terms"): sys.exit(f"{a.lead_id}: no lead with a contract")
    if a.kind == "sign" and lead.get("contract") != "sent": sys.exit(f"{a.lead_id}: contract is {lead.get('contract')}, not waiting for a signature")
    to, subject, body = reminder(lead, a.kind, evtime.today_ct().year)
    if "@" not in to: sys.exit(f"{a.lead_id}: no client email")
    print(f"To: {to}\nSubject: {subject}\n\n{body}")
    if a.dry_run: return
    mailer.save_draft(mailer.build(to, subject, body))
    print("saved in Eman's Drafts")


if __name__ == "__main__":
    main()
