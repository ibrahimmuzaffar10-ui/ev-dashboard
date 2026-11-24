"""Import Zelle payments from Eman's Chase alert emails (read-only IMAP via himalaya).

Usage: python3 zelle_import.py
Writes/updates the payments (payments.json, or Supabase when EV_BACKEND=supabase). Prints new payments.
Dedupe: new payments are keyed by the email's Message-ID, which never changes. Older ones were keyed
by the mailbox number (which can change if the mailbox is rebuilt); their Message-IDs are remembered
in `zelle_ids` as they are seen, so a renumbered mailbox can't import the same payment twice.
"""
import json, os, re, subprocess, email, html, sys
from email import policy
import evenv
import db

SENDER = evenv.need("EV_ZELLE_SENDER")  # bank alert sender

def hj(*args):
    r = subprocess.run(["himalaya", "--json", *args], capture_output=True, text=True, timeout=300)
    if r.returncode != 0: raise SystemExit(r.stderr[-300:])
    return json.loads(r.stdout)

def body_text(raw):
    m = email.message_from_bytes(raw, policy=policy.default)
    part = m.get_body(preferencelist=("plain", "html"))
    t = part.get_content() if part else ""
    if part and part.get_content_type() == "text/html":
        t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S | re.I)
        t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t)

def parse(t):
    amt = re.search(r"\$\s?([\d,]+\.\d{2})", t)
    who = (re.search(r"(?:^|\s)([A-Z][\w'.-]+(?: [A-Z][\w'.-]+){0,3}) sent you money", t)
           or re.search(r"(?:From|Sent by)\s*:?\s*([A-Z][\w'.-]+(?: [A-Z][\w'.-]+){0,3})", t))
    memo = re.search(r"Memo\s*:?\s*(.{0,80}?)(?:\s{2,}|Amount|Sent on|Transaction|$)", t)
    return (float(amt.group(1).replace(",", "")) if amt else None, who.group(1).strip() if who else "", (memo.group(1).strip() if memo else ""))

TRASH = "Deleted Messages"
failed_apply = False


def name_segments(l):
    """Each person's name on its own: the lead name split on &/and/commas/brackets, plus the names on its contract,
    so "Kiwi Lime & Mango Y" matches a payer named Kiwi Lime or Mango Y, never "Mango Lime"."""
    names = l["client"] + " & " + (((l.get("contract_terms") or {}).get("fields") or {}).get("client_names") or "")
    return [x for x in re.split(r"\s*(?:&|\band\b|,|\(|\)|/)\s*", names, flags=re.I) if x.strip()]


def over_total(l, p, pays, extra=0):
    """True when linking this payment would take the payments linked to the booking above its total."""
    total = l.get("total")
    if not total: return False
    linked = sum(float(x.get("amount") or 0) for x in pays if x.get("lead_id") == l["id"])
    return linked + extra + float(p.get("amount") or 0) > float(total) + 0.005


def ensure_plan(lead_id):
    """A deposit for a contract that was sent but has no payment plan yet: put the plan on the books first (the
    deposit then goes to the retainer line). Plans are NOT created at sending (review H1: unsigned contracts would
    show as money due / overdue)."""
    import threading, server
    with db.locked(threading.Lock()):
        d = db.load()
        l = next((x for x in d["leads"] if x.get("id") == lead_id), None)
        if not l or l.get("schedule") or not l.get("contract_terms"): return
        l["schedule"] = server.plan_from_terms(l["contract_terms"], l["contract_terms"].get("sign_by"))
        if l.get("retainer") not in ("paid", "partial"): l["retainer"] = "unpaid"
        db.store(d)


def apply_to_plan(email_id, lead_id):
    """A matched Zelle for a booking with a payment plan: credit it through the Mac server's /api/payment-apply
    (marks the deposit / next installments paid, updates paid + balance, links the payment). False = not applied;
    the caller then only links it, as before (it can still be applied by hand from "To match" after an undo)."""
    import urllib.request
    try: ensure_plan(lead_id)
    except Exception as ex:
        print("plan not created:", ex, file=sys.stderr); return False
    port = os.environ.get("EV_PORT", "8787")
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/payment-apply", data=json.dumps({"email_id": email_id, "lead_id": lead_id}).encode(),
                                 headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{port}"})
    try:
        urllib.request.urlopen(req, timeout=30).read(); return True
    except Exception as ex:
        print("apply skipped:", ex); return False


def main():
    pays = db.payments_all()
    ids = db.doc_read("zelle_ids") or {}            # mailbox number -> Message-ID, for older payments
    seen = {p["email_id"] for p in pays} | set(ids.values())
    envs = hj("envelope", "search", "-s", "500", f'from {SENDER} and subject "You received money with Zelle" order by date desc')["envelopes"]
    new, learned = [], False
    for e in envs:
        mid = e.get("message-id") or ""
        if e["id"] in seen:                        # an older payment: remember its permanent id
            if mid and ids.get(e["id"]) != mid:
                ids[e["id"]] = mid; learned = True
            continue
        if mid and mid in seen: continue
        raw = subprocess.run(["himalaya", "message", "read", "--raw", e["id"]], capture_output=True, timeout=120).stdout
        amount, sender, memo = parse(body_text(raw))
        p = {"email_id": mid or e["id"], "date": e["date"][:10], "amount": amount, "sender": sender, "memo": memo, "method": "Zelle (Chase)", "lead_id": None}
        pays.append(p); new.append(p); seen.add(p["email_id"])
    # Eman often deletes the Chase emails: read Deleted Messages too. Its message numbers are a different series than
    # the Inbox's, so only the permanent Message-ID counts as "seen" there. Older payments saved under an Inbox number
    # (no Message-ID learned yet) are matched by date + amount + sender, one record per email, so a payment already on
    # the books is never imported twice, while two real same-day payments of the same amount both count.
    import collections
    legacy = collections.Counter((str(p.get("date"))[:10], float(p.get("amount") or 0), (p.get("sender") or "").upper())
                                 for p in pays if str(p.get("email_id", "")).isdigit() and str(p.get("email_id")) not in ids)
    try:
        denv = hj("envelope", "search", "-m", TRASH, "-s", "500", f'from {SENDER} and subject "You received money with Zelle" order by date desc')["envelopes"]
    except SystemExit as ex:
        print("deleted folder skipped:", ex); denv = []
    for e in denv:
        mid = e.get("message-id") or ""
        if not mid or mid in seen: continue
        raw = subprocess.run(["himalaya", "message", "read", "--raw", "-m", TRASH, e["id"]], capture_output=True, timeout=120).stdout
        amount, sender, memo = parse(body_text(raw))
        key = (e["date"][:10], float(amount or 0), (sender or "").upper())
        if legacy[key] > 0:                     # already on the books under its old Inbox number
            legacy[key] -= 1; seen.add(mid); continue
        p = {"email_id": mid, "date": e["date"][:10], "amount": amount, "sender": sender, "memo": memo, "method": "Zelle (Chase)", "lead_id": None}
        pays.append(p); new.append(p); seen.add(mid)
    pays.sort(key=lambda p: p["date"], reverse=True)
    # auto-match payer name to a lead (unique full-name token match); leave unmatched for review
    try:
        leads = (db.load() if db.CLOUD else json.load(open(os.path.join(db.DATA_DIR, "tracker_data.json"))))["leads"]
        toks = lambda s: set(re.findall(r"[a-z]{3,}", (s or "").lower())) - {"and", "the", "via", "muhammad", "mohammad", "ali"}  # leak-check: allow: very common names excluded from fuzzy matching, not a person
        extra = {}                                  # amounts matched earlier in this run, per booking
        for p in pays:
            if p.get("lead_id") or p.get("personal") or p.get("other_income"): continue      # sorted payments are never auto-matched
            pt = toks(p["sender"])
            cands = [l for l in leads if pt and any(len(pt & toks(seg)) >= min(2, len(pt)) for seg in name_segments(l))]
            if len(cands) != 1: continue
            l = cands[0]
            if over_total(l, p, pays, extra.get(l["id"], 0)): continue   # more than the booking's total: a person decides
            extra[l["id"]] = extra.get(l["id"], 0) + float(p.get("amount") or 0)
            plan = any(not x.get("paid") for x in l.get("schedule") or []) or (bool(l.get("contract_terms")) and l.get("contract") in ("sent", "signed"))
            p["_match"] = (l["id"], l["client"], plan)
    except Exception as ex:
        print("match skipped:", ex)
    # 11/18: add only the new payments, then link matches one row at a time (re-checked under the lock), so a payment
    # matched / applied / marked personal in the app meanwhile is never overwritten by this run's older copy
    db.payments_add([{k: v for k, v in p.items() if k != "_match"} for p in new])
    for p in pays:
        if p.get("_match"):
            lid, client, has_plan = p["_match"]
            if has_plan:
                if not apply_to_plan(p["email_id"], lid):
                    print("left in To match (could not credit the plan):", p["email_id"], file=sys.stderr); failed_apply = True
                continue           # credited to the plan + linked, or left unmatched so it shows in "To match"
            def link(x, lid=lid, client=client):
                if not x.get("lead_id") and not x.get("personal") and not x.get("other_income"):
                    x["lead_id"] = lid; x["client"] = client
            try: db.payment_change(p["email_id"], link)
            except ValueError: pass
    if learned:
        db.doc_write("zelle_ids", ids)
    print(json.dumps(new, indent=1))
    print(f"{len(new)} new, {len(pays)} total")
    if failed_apply: sys.exit(2)          # watch.py reports it; the payment waits in "To match"


if __name__ == "__main__":
    main()
