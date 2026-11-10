"""Import Zelle payments from Eman's Chase alert emails (read-only IMAP via himalaya).

Usage: python3 zelle_import.py
Writes/updates the payments (payments.json, or Supabase when EV_BACKEND=supabase). Prints new payments.
Dedupe: new payments are keyed by the email's Message-ID, which never changes. Older ones were keyed
by the mailbox number (which can change if the mailbox is rebuilt); their Message-IDs are remembered
in `zelle_ids` as they are seen, so a renumbered mailbox can't import the same payment twice.
"""
import json, os, re, subprocess, email, html
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
    pays.sort(key=lambda p: p["date"], reverse=True)
    # auto-match payer name to a lead (unique full-name token match); leave unmatched for review
    try:
        leads = (db.load() if db.CLOUD else json.load(open(os.path.join(db.DATA_DIR, "tracker_data.json"))))["leads"]
        toks = lambda s: set(re.findall(r"[a-z]{3,}", (s or "").lower())) - {"and", "the", "via", "muhammad", "mohammad", "ali"}  # leak-check: allow: very common names excluded from fuzzy matching, not a person
        for p in pays:
            if p.get("lead_id"): continue
            pt = toks(p["sender"])
            cands = [l for l in leads if pt and len(pt & toks(l["client"])) >= min(2, len(pt))]
            if len(cands) == 1: p["lead_id"] = cands[0]["id"]; p["client"] = cands[0]["client"]
    except Exception as ex:
        print("match skipped:", ex)
    db.payments_save(pays)
    if learned:
        db.doc_write("zelle_ids", ids)
    print(json.dumps(new, indent=1))
    print(f"{len(new)} new, {len(pays)} total")


if __name__ == "__main__":
    main()
