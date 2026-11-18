# Data retention — Emanant HQ (proposal, nothing automated)

**Status: proposal for Ibrahim to decide. Nothing is erased automatically, and nothing will be until he says so.**
Not legal advice; confirm the numbers with an accountant/attorney.

## Why have a policy at all
Keeping client details forever means more to lose in a breach (see `docs/SECURITY.md`). Keeping too little means
losing what the business needs: tax records, contract proof, and booking stats. The middle ground is to keep the
**numbers** and remove the **personal details** once they are no longer useful.

## Proposed rules

| Data | Keep for | Then |
|---|---|---|
| Booked/completed leads, contracts, payments | **7 years** after the event (IRS: 3 years normally, up to 7 in some cases; contract disputes in Texas: 4 years) | Review once a year; keep if a client might come back (family/repeat) |
| Lost/ghosted leads | **3 years** after the last contact | **Anonymize**: name → "Former lead", email/phone/notes cleared. Status, reason, dates, service and channel stay, so conversion stats keep working |
| Alerts (email notices) | 1 year after handled | Clear the message text; keep type + date |
| Zelle payment records | Same as the booking they belong to (personal ones: 1 year) | Sender name cleared; amount + date stay |
| Backups | 30 most recent (already automatic) | Older ones are replaced automatically |

## How it would run (only after approval)
A yearly, **manual** step (e.g. every January): a script lists what qualifies, Ibrahim reviews the list, then
confirms. Before anything changes, a full backup is taken and kept separately. No automatic schedule.

## Decision needed
1. Keep everything as-is (today's behavior), **or** adopt the rules above with the yearly manual review?
