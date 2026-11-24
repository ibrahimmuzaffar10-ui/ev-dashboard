"""Email a client their DocuSeal signing link from Eman's business email (queued in the outbox; the Mac sends it
and keeps a copy in Eman's Sent folder). The wording is the approved standard (Ibrahim, 11/23): only the client's
first name, event, date, deposit, link and sign-by date change.

    .venv/bin/python scripts/send_contract.py L000 https://docuseal.com/s/XXXX [--dry-run] [--resend]

Marks the lead's contract as "sent" and keeps the link on the contract record. The payment plan goes on the books
when the deposit arrives (zelle_import) or the contract is signed, never before (unsigned = not money due).
Refuses to send twice (--resend to override) or after the sign-by date. Run with EV_BACKEND=supabase.
"""
import argparse, datetime, os, sys, threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import evenv, db  # noqa: E402,F401

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def nice_date(iso, weekday=True, year_if_not=None):
    d = datetime.date.fromisoformat(str(iso)[:10])
    s = (f"{DAYS[d.weekday()]} " if weekday else "") + f"{MON[d.month - 1]} {d.day}"
    return s + (f", {d.year}" if d.year != year_if_not else "")


def money(v):
    v = float(v)
    return f"${v:,.0f}" if v == int(v) else f"${v:,.2f}"


def contract_email(terms, link, this_year):
    """(to, subject, body) in the approved wording."""
    f = terms["fields"]
    words = [w for w in (f.get("first_names") or f.get("client_names") or "").replace("&", " ").split()
             if w.rstrip(".").lower() not in ("dr", "mr", "mrs", "ms", "miss")]
    first = words[0] if words else "there"
    event = (f.get("session_type") or "event").strip().lower()
    when = nice_date(terms["days"][0]["date"], True, this_year)
    sign_by = nice_date(terms["sign_by"], False, this_year)
    deposit = money(terms["retainer"]) + " " if terms.get("retainer") else ""
    subject = f"Your Emanant Visuals contract: please sign by {sign_by}"
    body = (f"Hi {first},\n\n"
            f"Thank you so much for your patience! Your contract for your {event} on {when} is ready. "
            f"You can review and sign it here:\n\n{link}\n\n"
            f"Please sign by {sign_by} so the link doesn't expire. Your date is reserved once the contract is signed "
            f"and the {deposit}deposit is received (Zelle details are in the contract).\n\n"
            f"If you have any questions or anything needs changing, just reply to this email.\n\n"
            f"We're so excited to work with you!\n\n"
            f"Eman\nEmanant Visuals\n")
    return (f.get("client_email") or "").strip(), subject, body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lead_id"); ap.add_argument("link"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resend", action="store_true", help="send again although this contract was already sent")
    a = ap.parse_args()
    if not a.link.startswith("https://docuseal.com/s/"):
        sys.exit("link must be a DocuSeal signing link (https://docuseal.com/s/...)")
    import evtime
    with db.locked(threading.Lock()):
        d = db.load()
        lead = next((l for l in d["leads"] if l.get("id") == a.lead_id), None)
        if not lead or not lead.get("contract_terms"):
            sys.exit(f"{a.lead_id}: no lead with a contract")
        t = lead["contract_terms"]
        if not t.get("days") or not t["days"][0].get("date"):
            sys.exit(f"{a.lead_id}: the contract has no event date")
        if str(t.get("sign_by") or "") < evtime.today_ct().isoformat():
            sys.exit(f"{a.lead_id}: the sign-by date {t.get('sign_by')} has passed: re-issue the contract first")
        if (t.get("sent_on") or t.get("docuseal_link")) and not a.resend:
            sys.exit(f"{a.lead_id}: already sent on {t.get('sent_on')} ({t.get('docuseal_link')}); use --resend to send again")
        other = next((l["id"] for l in d["leads"] if l is not lead and (l.get("contract_terms") or {}).get("docuseal_link") == a.link), None)
        if other:
            sys.exit(f"{a.lead_id}: that link belongs to {other}")
        to, subject, body = contract_email(t, a.link, evtime.today_ct().year)
        if "@" not in to:
            sys.exit(f"{a.lead_id}: the contract has no client email")
        print(f"To: {to}\nSubject: {subject}\n\n{body}")
        if a.dry_run:
            return
        t["docuseal_link"] = a.link; t["sent_on"] = evtime.today_ct().isoformat()
        lead["contract"] = "sent"
        lead["action_note"] = f"{evtime.today_ct().isoformat()}: contract link emailed to the client; waiting for signature + deposit."
        db.outbox_enqueue(to, subject, body)       # joins this save's transaction: queued only if the save commits
        db.store(d)
    print("queued")


if __name__ == "__main__":
    main()
