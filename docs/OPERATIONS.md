# Emanant HQ — what to do when something is off

Plain-language procedures (Stage 2, phases 10–11). The website is https://ev-dashboard-tan.vercel.app;
the Mac copy is http://127.0.0.1:8787 (same data, from Supabase).

## Who does what, where
| Part | Runs on | If it stops |
|---|---|---|
| Dashboard website + saving edits | Vercel + Supabase (cloud) | See "Website down" |
| Email watcher (new inquiries, client replies, DocuSeal, Zelle) | The Mac, every 2 h + 6:45 AM and 9 PM + the **🔄 Check email now** button (works from the phone too: the Mac checks within a minute, or as soon as it's back on) | See "Mac off" |
| Sending email (contract drafts, replies from the dashboard) | The Mac (outbox, every 1 min) | Emails wait in the "Emails waiting" banner and go out when the Mac is back |
| Calendar sync, 7 AM / 10 PM brief, docs copy, nightly backup, Monday report | The Mac | They catch up on the next run after the Mac is back |

## Mac off or asleep (phase 10)
**What still works:** the website, all edits, contract creation (the email queues).
**What pauses:** new-email alerts, Zelle import, sending, calendar, brief, backup.

1. The website shows a red **"💻 Mac offline"** banner after 15 min; healthchecks.io emails Ibrahim about an hour after the Mac goes quiet, or when email checks keep failing (the 1-min sender job checks in only while the last email check succeeded within 2.5 h).
2. While it is off, check Eman's inbox on her phone for new inquiries and reply from there (her phone's replies are picked up automatically later: the watcher reads her Sent folder).
3. When the Mac is back: nothing to do. The watcher looks back from its **last successful run** (at least 3 days), so no email is skipped; queued emails send within a minute; the brief and backup run on their next hourly check.
4. Queued emails that waited over **12 hours** are **not** sent automatically (they could be out of date): the banner shows them with **Send again / Cancel**.

**Keep-awake:** on the charger the Mac never sleeps while the lid is open (`pmset` AC sleep = 0). On battery it sleeps after ~10 idle minutes; closing the lid always sleeps it. Laptop travels → gaps are expected and safe (step 3).

## Website down — Vercel problem (phase 11)
Moving to another host for good: `docs/HOSTING.md`.

1. On the Mac, open **http://127.0.0.1:8787**: the same dashboard on the same Supabase data, with saving. It is always running (launchd keeps it alive), so this fallback is up in **< 1 min**.
2. Nothing else changes: the Mac jobs never depend on Vercel.
3. Second host (only if Vercel is gone for good): any Python host that can run `api/index.py` with the environment variable names in `.env.example` (`EV_*`, Supabase URL/anon key, `EV_SELFTEST_TOKEN`, `CRON_SECRET`). Check it with `GET /api/_selftest` (header `X-EV-Selftest`) → 200. Not rehearsed yet: needs an account Ibrahim chooses.

## Database down — Supabase problem
- Short outage: wait. The Mac jobs retry on their own (the watcher keeps emails unseen until they are saved; the outbox never re-sends an interrupted email). healthchecks.io alerts if the watcher can't reach the database.
- Long outage (hours/days) and the business needs the dashboard: roll back to the old Mac app from the **newest nightly backup**, no Supabase needed: `.venv/bin/python scripts/restore_local.py ~/EmanantHQ-rollback` → then runbook **R5** (Ibrahim's OK; overwrites the frozen JSON after copying it aside). Anything saved after that night's backup must be re-entered.

## Testing without touching live data
After the cutover, the integration tests run only against a private local copy:
`.venv/bin/python scripts/testdb.py run .venv/bin/python scripts/test_step2.py <scratch dir with snap/>` (same for test_step3/4).
Run directly against the live database they refuse (`db.refuse_after_cutover`).
File-mode tests (`test_local_guard.py`, `test_step8.py`) run with `EV_ALLOW_JSON=1` (scratch files only).

## Removing a lead safely
`.venv/bin/python scripts/lead_admin.py delete <id> --name "<exact client name>"` (dry run) → add `--yes`.
Refuses booked/completed leads, signed contracts and any money; keeps a private copy in Application Support.
