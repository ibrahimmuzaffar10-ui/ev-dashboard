---
created: 2026-11-09
tags: [emanant-visuals, emanant-hq, migration, plan]
status: draft — decisions applied 11/9, awaiting final approval
supersedes: Cloud Migration Roadmap v1
related: Emanant Visuals, Dashboard Spec, Emanant HQ on free cloud stack
---
# Emanant HQ: Cloud Migration Roadmap v2

> **Source of truth from 2026-11-10:** this file in the repo. It started as an Obsidian vault note (copy kept there, no longer updated). Update the Status log here at every phase boundary.

v2 = v1 after two adversarial reviews (technical + security), 11/9. Every blocker they found is fixed below. A change log is at the bottom.

Moves the local dashboard (`~/EmanantHQ`, localhost:8787) onto **GitHub + Vercel Hobby (free) + Supabase Free**. The mail and calendar syncs stay on the Mac permanently. Later: a full Next.js rebuild, mobile-first.

## Ground rules
- **Public repo, zero sensitive info in it (Ibrahim 11/9).** Client data, personal addresses, phone numbers, contract wording, prices and templates live in Supabase (`settings` table or private Storage) or in gitignored local config. Git holds only generic code.
- **Email sending is local:** the cloud queues emails in an outbox; the Mac sends them. Eman's iCloud app password stays in the Mac Keychain.
- **One writer at a time**, same as today: every save is one database transaction holding a lock.
- **The cloud is read-only until cutover.** The local dashboard is the only place edits happen until Phase 7.
- **Each phase starts only when the previous one passes its test.** No dates.
- Structure first, UI later (Dashboard Spec).

## Verified platform facts (11/9)
| Fact | Impact |
|---|---|
| Vercel Hobby = non-commercial use only | Accepted risk. Exit plan = Phase 11 |
| Vercel Python: class must be named `handler`; read-only filesystem except `/tmp`; 300 s max; 4.5 MB request limit; server clock is UTC and `TZ` can't be set | Phase 4/5 fixes |
| Supabase Free: **no backups**; Storage isn't in DB backups; pauses after 7 days of low activity (data is kept) | Phase 7 backups, Phase 9 keep-alive |
| Supabase built-in email only reaches project team members, 2/hour | Login can't depend on it |
| Supabase Free direct DB connection is IPv6-only; serverless must use the transaction pooler (port 6543, no prepared statements) | Phase 4 |
| Supabase sign-ups are **on** by default | Turn off in Phase 0 |
| GitHub secret scanning + push protection are free and **on** for this public repo | Keep on; also enable non-provider patterns; plus a local `gitleaks` hook |
| healthchecks.io Hobbyist plan: free, 20 monitored jobs | Mac-offline alert (Phase 9) |

---

## Stage 1: Lift onto the rails

| # | Phase | What changes | Pass/fail test |
|---|---|---|---|
| 0 | **Access + guardrails** | GitHub ✅. Repo **public** ✅; turn on secret-scanning non-provider patterns. `supabase login` (browser). **Turn off sign-ups and anonymous sign-ins.** Note the Supabase region and pin the Vercel function region next to it. Vercel team = owner only | Settings screenshots confirm sign-ups off · regions match |
| 1 | **Repo scaffold** | **Allowlist `.gitignore`**: ignore everything, then un-ignore only code (`*.py`, `*.html`, `vercel.json`, `requirements.txt`, `supabase/`, later `web/`). **Sensitive-config extraction:** hardcoded addresses (server.py 2, watch.py 2, calendar_sync.py 1, zelle_import.py 1) → gitignored `.env.local` (Mac) / Vercel env; contract wording + prices + Zelle phone (`contract_final_content.py`) and the questionnaire price → private Storage, loaded by the renderer at runtime; prices and reply templates in `dashboard_template.html` → `settings` rows served by `/api/data`; `make_drafts_1107.py` stays local only. `gitleaks` + a custom scan that loads every client name/email/phone from the live JSON and greps the staged files, run as a pre-commit and pre-push hook | Staged tree: **0** data files · **0** client-token hits · **0** email addresses, phone numbers or `$` prices · **0** gitleaks hits · `vercel.json` is tracked · contract renders identical to VFinal with the content loaded from Storage |
| 2 | **Schema v1** | Each list item stored **exactly as in the JSON** (`raw`, type json) + its list position; searchable columns (id, status, emails, amounts, lead_id, …) are **generated from it by Postgres**. Tables: leads, alerts, vendors, payments, **emails** (replaces the seen list, with a status), app_state, settings. **No changelog** (Ibrahim 11/10). Dates stay text. IDs stay `L###`/`A####`. RLS: allowlist table keyed on the user ID, deny by default, read-only. Private bucket `contracts`. Details: *Schema v1* below | **Before applying:** `scripts/profile_keys.py` on the live JSON → **0** blockers · `select rolbypassrls from pg_roles where rolname='postgres'` → **true** · local `supabase/tests/rls_test.sql` **113/113**. **After applying** (with `live_seed.sql` in place): `scripts/test_rls_live.py` → anon reads **0** rows · non-allowlisted user reads **0** rows · allowlisted user reads **every** seeded row · all three refused on insert/update/delete · anon Storage GET **≠ 200** · **0** fails; then `live_unseed.sql` |
| 3 | **Data migration** | JSON → tables, **plus** contract files: Contract Drafts (10), Signed (2), pending (3), VFinal templates → Storage under `leads/<id>/…`; file paths in `contract_terms` rewritten to Storage keys | Row counts exact (leads **116**, payments **37**, vendors **40**, alerts **28**, emails **873**) · `load()` reproduces the JSON **exactly** (minus the dropped changelog), including missing-vs-null · file count + SHA-256 match for every file |
| 4 | **Swap the data layer** | Each POST = **one Postgres transaction** with an advisory lock → load → same route code → write inserts, updates **and deletes** (raw json sent as text, never via jsonb; no changelog line). The 14 route handlers stay unchanged. Pooler connection (`pg_advisory_xact_lock`, prepared statements off). Dedicated `ev_server` DB role with only the rights it needs, instead of `postgres`. All dates via `America/Chicago` helpers. Renderer writes to `/tmp`, then uploads to Storage. **New job routes** for the Mac (payments, brief, seen-list, heartbeat, a narrow job-context read), signed with an HMAC secret that can be rotated. Errors return a generic message + request ID; logs hold IDs only. **Email sending → outbox** (cloud queues, Mac sends) | **20** parallel writes → **0** lost, **0** duplicate IDs · fold-alerts path deletes correctly · lead created at 11:30 PM CT gets today's CT date · tests use a **TEST** lead/alert only (no real client email) · jsdom test committed and passing |
| 5 | **Deploy + login** | Vercel `handler` + catch-all rewrite + `requirements.txt` + bundled HTML/renderers. **Minimal login page + HttpOnly session cookie** (so links like `/docs` and `/calendar` work). Deny by default on **every** route. Secrets in Production only; previews use no real data. Cloud **writes return 403** until Phase 7 | Eman's iPhone on cellular: log in → load **< 3 s** · logged out → **401** on every route incl. `/docs/*` · non-allowlisted account → **403** · server-side p95 `/api/data` **< 800 ms** |
| 6 | **Repoint the jobs (Mac)** | Inventory every JSON consumer: watch, zelle_import, brief, calendar_sync, build_tracker, **and the Hermes weekly-report prompt**. `API_BASE` env var in each. Watcher fixes: the `emails` row is written **inside the same transaction as the alert** (route returns `dup` if it exists), so "seen" only happens on success; failed emails retried with a cap (`attempts`); fallback keys get a mailbox prefix; `alert-new` idempotent on `email_id`; `last_ok` only when every post succeeded; lock file against overlapping runs; payments keyed on Message-ID. **Watcher stays on launchd**. Shadow mode = separate state file, no notifications, no Zelle run, no emails | 48 h shadow: email key sets differ by **0** · API blocked 30 min then restored → **0** lost emails · each job gets **401** without the secret and succeeds with it |
| 7 | **Cutover + backups** | Stop the local server + watcher → truncate and reload all tables + Storage → verify counts → enable cloud writes → start jobs on the cloud. **Nightly backup:** `supabase db dump` + Storage sync to the Mac (FileVault-encrypted), 30 days kept. No second copy (Ibrahim 11/9). Old `backups/` folder (202 files) archived, encrypted, offline | **Rollback drill passes before the 14-day clock starts** (export → local server → KPIs match) · **14** days with **0** rollbacks and **0** data mismatches · first restore into a scratch project succeeds |

### Schema v1 (Phase 2 design)
File: `supabase/migrations/20261110000000_schema_v1.sql`. Revised 11/10 after an adversarial review (see Change log).

| Table | Holds | Key | Generated (searchable) columns |
|---|---|---|---|
| `leads` | `tracker_data.leads` | `id` (`L###`) | client, status, event, src_email, alt_email, total, paid |
| `alerts` | `tracker_data.alerts` | `id` (`A####`) | type, at, lead_id, email_id (indexed, **not** unique), from_email, done |
| `vendors` | `tracker_data.vendors` | position | name |
| `payments` | `payments.json` | `email_id` | date, amount, lead_id |
| `emails` | `watch_state.seen` + future watcher runs | email key | — own columns: folder, status (`pending`/`processed`/`skipped`/`failed`), attempts, alert_id. **No sender, subject or body** |
| `app_state` | finance, ignore/watch senders, schema, generated, watch_state since/last_ok, brief files | (`file`, `key`) | — |
| `settings` | prices, reply templates, privacy options (never in git) | `key` | — |
| `private.app_users` | the login allowlist (user ID + label, no names) | `user_id` | not reachable through the API |
| Storage `contracts` | contract files (Phase 3) | `leads/<id>/…` | private, 25 MB, PDF/DOCX/JSON only |

- **Exact round trip:** every item is kept as-is in `raw` (json keeps key order, missing-vs-null, `500` vs `500.0`). `load()` = raw ordered by position. The generated columns can't drift from raw and give NULL (not an error) for odd values.
- **Security:** RLS + FORCE RLS on every table. `anon`: no privileges. `authenticated`: SELECT only, and only if the user ID is on the allowlist. **No write policies** (read-only until Phase 7). Future tables and functions are closed until granted on purpose.
- **Not in v1 on purpose:** a changelog (dropped) · enum checks and the alert→lead link (the live data may hold values the code never wrote) · outbox / heartbeat / job tables (Phase 4) · requiring MFA in the database (decision pending).

---

## Stage 2: Harden the local syncs
The email watcher, Zelle import, brief, calendar sync and outbox sender stay on the Mac permanently (Eman's business mail is iCloud, IMAP only).

| # | Phase | What changes | Pass/fail test |
|---|---|---|---|
| 8 | **Faster watcher** | Every **1 min** under launchd with the lock file. A near-instant IMAP IDLE listener only after a spike (needs Python 3.14 or `imapclient`; the system Python 3.9 can't) | Median email → alert **< 2 min** over 7 days · **0** missed |
| 9 | **Heartbeat + Mac-offline alert** | **Simplest version:** a free healthchecks.io check. The watcher pings its URL after each successful run (one line of code; URL kept in `.env.local`). No ping for 15 min → email to Ibrahim + Eman; another email when it's back. Plus a dashboard banner "Mac offline · N emails queued" from the Supabase heartbeat, and a daily Vercel cron query that keeps Supabase from pausing | Lid closed → email to both in **≤ 20 min** · "back" email after reopening · 7 days with the Mac off → project not paused |
| 10 | **Keep-awake + travel procedure** | Power settings so the Mac doesn't sleep on the charger. One-page "Mac is off" procedure (who checks Eman's mail by hand) | Heartbeat gaps **< 1 h/day** over 7 days |
| 11 | **Vercel exit drill** | `server.py` + `db.py` must still run locally against Supabase (1-min fallback). A second host documented with the same env var names, tested once | Local fallback up in **≤ 1 min** · second host serving in **≤ 30 min** |

## Stage 3: Next.js rebuild, mobile-first
In `web/` in the same repo, on the same Supabase. Can start any time after Phase 7.

| # | Phase | What changes | Pass/fail test |
|---|---|---|---|
| 12 | **Scaffold** | Next.js (App Router, TypeScript), Supabase login, own Vercel project (Root Directory `web/`) | Both logins work on a phone · reads go through RLS with the user's own session, no admin key in the browser |
| 13 | **Screens, read-only** | Dashboard, Pipeline, Bookings, Calendar, Vendors, Financials, phone first | Numbers match the old app · no sideways scroll at **375 px** · Lighthouse mobile **≥ 90** |
| 14 | **Business rules → database** | Alert merging, ID generation (sequences), validation, payment schedules become Postgres functions. **The Python server and the Mac jobs switch to them too**, so only one copy of each rule exists | Same results as the Python version on **100%** of a replayed test set |
| 15 | **Editing** | All actions from the phone | Every action works from Eman's iPhone · both apps show identical data |
| 16 | **Live updates + push** | Supabase Realtime. Home-screen app (iOS 16.4+), login done **inside** the installed app. Sender = database webhook → Vercel function with VAPID keys | New alert on a phone **< 5 s** · push reaches both phones with the Mac off |
| 17 | **Contracts** | The Python renderer moves into the `web/` project as a Python function (or a renderer-only project) | Rendered contract matches VFinal page for page |
| 18 | **Switch** | New app on the main URL; old Python UI retired | Mac jobs pass against the new endpoints · **14** days with no fallback |

## Stage 4 (later, optional)
Split `schedule` + `contract_terms` into tables · custom domain `hq.emanantvisuals.com` (**CNAME only at GoDaddy; never touch nameservers or the iCloud MX/TXT records**) · retention policy (anonymize lost/ghosted leads after 2–3 years; keep contracts + payments ~4+ years; not legal advice, confirm with an attorney) · one-page breach checklist (revoke the app password, rotate keys, decide on client notice).

---

## Decisions
| Decision | Status |
|---|---|
| Stack: GitHub + Vercel Hobby + Supabase Free | ✅ 11/9 (Hobby non-commercial clause = accepted risk; exit drill = Phase 11) |
| Syncs stay local on the Mac permanently | ✅ 11/9 |
| Logins: Ibrahim + Eman only | ✅ 11/9 |
| Eventual Next.js rebuild, mobile-first | ✅ 11/9 → Stage 3 |
| No dates, phase-gated | ✅ 11/9 |
| Repo visibility | ✅ **Public** (Ibrahim 11/9). Note: Vercel only requires public for organization-owned repos; public is still fine here because nothing sensitive goes in git, and it keeps GitHub's free secret scanning |
| Sensitive info | ✅ Never in git: Supabase (`settings` / private Storage) or gitignored local config |
| Email sending | ✅ Local outbox: cloud queues, Mac sends; app password stays in Keychain |
| Login method | ⏳ Default unless Ibrahim objects: email + password; Ibrahim creates both users himself in the Supabase dashboard so no password passes through chat |
| Second backup copy | ✅ Not needed (Ibrahim 11/9); nightly dump on the Mac only |
| Mac-offline alert | ✅ healthchecks.io free, email to both, plus the dashboard banner |
| Changelog | ✅ **Not migrated, no table** (Ibrahim 11/10). The brief loses its "dashboard edits" lines; the old entries stay in the JSON on the Mac |
| Seen list → `emails` table with a status | ✅ Ibrahim 11/10 |
| Store each item exactly as in the JSON + generated columns | ⏳ Proposed 11/10 (Claude), **replaces my first draft** (typed columns + key-order/extra bookkeeping), after the adversarial review found a blocker and two exactness bugs in it |
| Storage test = "anon GET ≠ 200" instead of "= 403" | ⏳ Proposed 11/10. Supabase answers 400/404 for private objects |
| Require MFA (TOTP) for reading data, not only for login settings | ⏳ Open: safer (a stolen password alone reads nothing), but Phase 5's login page must then ask for the 6-digit code |

## Change log v1 → v2
| Finding (reviewer) | Fix |
|---|---|
| Lost/duplicate data with concurrent writes (both) | Phase 4: one transaction + advisory lock per save; parallel-write test |
| `store()` diff never deletes; changelog has no key (tech) | Phase 4: inserts/updates/deletes; changelog insert-only |
| Null vs missing keys crash the code; Decimal breaks JSON (tech) | Phase 2 defaults + Phase 3 exact round-trip test |
| Jobs write JSON directly; no routes for them (tech) | Phase 4 job routes; Phase 6 full consumer inventory |
| Vercel wrapper as written runs nothing (tech) | Phase 5 `handler`, rewrite, `/tmp`, bundled files |
| Login needs HTML changes + JWT verification (tech) | Phase 5 login page + session cookie |
| Watcher loses emails when the API fails (security) | Phase 6 seen-after-2xx, idempotent alerts, outage test |
| App password on Vercel exposes Eman's whole iCloud (security) | Outbox, decided 11/9 |
| Magic links won't deliver; sign-ups open (both) | Phase 0 sign-ups off; password login; non-allowlisted test |
| RLS tests prove little; service role bypasses RLS (security) | Phase 2 tests; Phase 5 deny-by-default on every route |
| Two systems writing during overlap (both) | Cloud read-only until Phase 7; shadow mode with no side effects |
| No real backups; Storage not covered (both) | Phase 7 nightly dump + Storage sync + restore drill (second copy declined) |
| Contract files not migrated (both) | Phase 3 Storage upload + checksums |
| `*.json` ignore hides `vercel.json`; name-based excludes fragile (both) | Phase 1 allowlist `.gitignore` + PII scan hook |
| UTC server clock shifts dates after ~6–7 PM CT (tech) | Phase 4 Chicago helpers + 11:30 PM test |
| Shared secret = full access, no rotation (security) | Phase 4 HMAC, route-scoped, two keys for rotation |
| Mac-offline only visible in the app; Supabase may pause (security) | Phase 9 healthchecks.io email + daily keep-alive |
| No Vercel exit plan (security) | Phase 11 drill |
| Hermes cron: no overlap guard, PATH, single point of failure (both) | **Reversed my earlier call:** watcher stays on launchd, plus a lock file |
| Tests unsafe (would email real clients) or unmeasurable (tech) | TEST lead/alert only; jsdom test committed; rollback drill |
| Stage 3 kept two copies of the rules (tech) | Phase 14 moves the Python server + Mac jobs to the PG functions |
| **Schema v1 adversarial review (11/10):** codec wrote NULL into NOT NULL alert columns (blocker) | Redesign: raw json + generated columns; no codec |
| Live test passed on empty tables | Seed one TEST row per table + a test PDF; the allowlisted user must see them |
| Future functions callable by anon (PUBLIC execute) | Global default-privilege revoke + test |
| Unique alert `email_id` → error after the questionnaire email was already sent | Plain index (alert-new dedupes already) |
| Pre-check missed id format / missing keys | `profile_keys.py` blocks on them |
| json written via jsonb loses key order | Documented in the migration + Phase 4 |
| Server as `postgres` = full admin; session lock breaks on the pooler | Phase 4: `ev_server` role, `pg_advisory_xact_lock`, no prepared statements |
| Watcher retries could repeat side effects | Phase 6: emails row in the same transaction as the alert, capped retries |
| Tests counted any error as "refused" | Every refusal must be SQLSTATE 42501 |

## Status log
- 2026-11-10 — **Phase 2 revised, not applied.** Ibrahim: drop the changelog; seen list → `emails` table with a status. Adversarial review (15 findings: 1 blocker, 2 high) → redesign: each item kept exactly in `raw` json with generated columns (codec removed). Local tests on Postgres 16 with a Supabase stand-in: **113/113**; 3 deliberately broken versions (allowlist bypassed, future-function lock removed, write grant added) each caught. Live-test logic against a fake server: 100/100. Leak check 0 hits (generic only; name check + gitleaks need the Mac).
- 2026-11-10 — **Phase 2 drafted, not applied.** Taken over from Hermes by Claude (cloud session, branch `claude/gifted-dijkstra-maze19`; no access to the Mac, live JSON or Supabase from there). Migration + RLS + Storage written; columns built from every key the code reads/writes (server, watch, zelle_import, brief, calendar_sync, dashboard). Local tests on Postgres 16 with a Supabase stand-in: RLS/privilege test **80/80** (and a deliberately broken policy is caught: 8 fails); codec round trip **8/8**. Leak check 0 hits (generic only: live-data name check and gitleaks need the Mac). Waiting on: key profile from the live JSON, Ibrahim's approval, then apply + live test.
- 2026-11-10 — **Phase 1 passed.** Pushed `c325d31` to `main` (public). GitHub shows exactly the 18 files; local HEAD = remote HEAD; 0 secret-scanning alerts; pre-push leak check + gitleaks passed.
- 2026-11-10 — **Phase 1 prepared, not pushed.** Repo lives at `~/repos/ev-dashboard` (Ibrahim: never delete or move files in `~/EmanantHQ` or the vault; the repo holds COPIES of the code). Local commit `c325d31`, 18 files, authored as ibrahimmuzaffar10-ui (noreply). Addresses/prices moved to gitignored `.env.local` (loaded by `evenv.py`), contract wording loaded from `EV_CONTRACT_CONTENT_DIR`, data from `EV_DATA_DIR` (still `~/EmanantHQ`). Allowlist `.gitignore`; `scripts/check_leaks.py` + gitleaks in pre-commit/pre-push. Tests: leak check 0 hits on 18 files (373 live values + 190 name words); planted fake email/price and a real client name both blocked; repo copy on :8788 vs live :8787 byte-identical on /api/data, /api/brief, /calendar, /api/calendar, /docs/*; HTML identical except one 57-char allow comment; contract + questionnaire DOCX/PDF text identical (8/8, 5/5 pages). Awaiting Ibrahim's push approval.
- 2026-11-09 — **Phase 0 passed.** Supabase project `ev-dashboard` (org emanant-visuals, us-east-1) linked from `~/EmanantHQ/supabase/`. Sign-ups + email sign-ups off, anonymous off, min password 12; MFA (TOTP) and email confirmations kept ON (the default config.toml would have turned them off; local config aligned to remote first). Live probe: signup → 422 signup_disabled, anonymous → 422. Vercel region = `iad1` (next to us-east-1). Vercel Hobby team is single-user by design. GitHub non-provider secret patterns can't be enabled on this repo; standard scanning + push protection stay on.
- 2026-11-09 — Decisions applied: public repo with zero sensitive info, local outbox, no second backup, healthchecks.io alert.
- 2026-11-09 — v1 drafted. Two adversarial reviews run (technical + security); claims spot-checked against code and docs. v2 written.
