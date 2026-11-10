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
| 2 | **Schema v1** | Columns built from the **real key union**, not v1's list (adds event_text, venue, quote, notes, action_note, replied, ig_ref, price_obj, source; alerts: at, detail, email_id **unique**, from_email, unread, ignored, clarify fields; payments: memo, client). Changelog = `at, by, client, field, id, old json, new json`. Dates stay **text** (data has `''` and nulls). `count` default 1, `email_ids` default `[]`. IDs stay `L###`/`A####`. RLS: allowlist table keyed on the user ID, deny by default. Private bucket `contracts`, no public policy. **Lossless round-trip columns** (`pos`, `key_order`, `extra`) — see *Schema v1* below | **Before applying:** `scripts/profile_keys.py` on the live JSON → **0** blockers · local `supabase/tests/rls_test.sql` **80/80** · `tests/test_db_codec.py` **8/8**. **After applying:** `scripts/test_rls_live.py` → anon reads **0** rows · a signed-in user **not** on the allowlist reads **0** rows · anon + stranger + allowlisted insert/update/delete refused · anon Storage GET **≠ 200** (Supabase answers 400/404 for a private bucket, not 403) · **0** fails |
| 3 | **Data migration** | JSON → tables, **plus** contract files: Contract Drafts (10), Signed (2), pending (3), VFinal templates → Storage under `leads/<id>/…`; file paths in `contract_terms` rewritten to Storage keys | Row counts exact (leads **116**, payments **37**, vendors **40**, changelog **270**, alerts **28**, seen **873**) · `load()` reproduces the JSON **exactly**, including missing-vs-null · file count + SHA-256 match for every file |
| 4 | **Swap the data layer** | Each POST = **one Postgres transaction** with an advisory lock → load → same route code → write inserts, updates **and deletes**; changelog insert-only. The 14 route handlers stay unchanged. Pooler connection. All dates via `America/Chicago` helpers. Renderer writes to `/tmp`, then uploads to Storage. **New job routes** for the Mac (payments, brief, seen-list, heartbeat, a narrow job-context read), signed with an HMAC secret that can be rotated. Errors return a generic message + request ID; logs hold IDs only. **Email sending → outbox** (cloud queues, Mac sends) | **20** parallel writes → **0** lost, **0** duplicate IDs · fold-alerts path deletes correctly · lead created at 11:30 PM CT gets today's CT date · tests use a **TEST** lead/alert only (no real client email) · jsdom test committed and passing |
| 5 | **Deploy + login** | Vercel `handler` + catch-all rewrite + `requirements.txt` + bundled HTML/renderers. **Minimal login page + HttpOnly session cookie** (so links like `/docs` and `/calendar` work). Deny by default on **every** route. Secrets in Production only; previews use no real data. Cloud **writes return 403** until Phase 7 | Eman's iPhone on cellular: log in → load **< 3 s** · logged out → **401** on every route incl. `/docs/*` · non-allowlisted account → **403** · server-side p95 `/api/data` **< 800 ms** |
| 6 | **Repoint the jobs (Mac)** | Inventory every JSON consumer: watch, zelle_import, brief, calendar_sync, build_tracker, **and the Hermes weekly-report prompt**. `API_BASE` env var in each. Watcher fixes: mark seen **only after a 2xx**; `alert-new` idempotent on `email_id`; `last_ok` only when every post succeeded; lock file against overlapping runs; payments keyed on Message-ID. **Watcher stays on launchd**. Shadow mode = separate state file, no notifications, no Zelle run, no emails | 48 h shadow: email key sets differ by **0** · API blocked 30 min then restored → **0** lost emails · each job gets **401** without the secret and succeeds with it |
| 7 | **Cutover + backups** | Stop the local server + watcher → truncate and reload all tables + Storage → verify counts → enable cloud writes → start jobs on the cloud. **Nightly backup:** `supabase db dump` + Storage sync to the Mac (FileVault-encrypted), 30 days kept. No second copy (Ibrahim 11/9). Old `backups/` folder (202 files) archived, encrypted, offline | **Rollback drill passes before the 14-day clock starts** (export → local server → KPIs match) · **14** days with **0** rollbacks and **0** data mismatches · first restore into a scratch project succeeds |

### Schema v1 (Phase 2 design)
Files: `supabase/migrations/20261110000000_schema_v1.sql`, codec `db_codec.py`.

| Table | Holds | Key | Notes |
|---|---|---|---|
| `leads` | `tracker_data.leads` | `id` (`L###`) | 28 typed columns + `contract_terms`, `schedule` as json (split in Stage 4) |
| `alerts` | `tracker_data.alerts` | `id` (`A####`) | `email_id` **unique** (alert-new idempotency); `count` default 1; `email_ids` default `[]` |
| `vendors` | `tracker_data.vendors` | `row_id` (internal) | no id in the JSON |
| `payments` | `payments.json` | `row_id` (internal) | `email_id` unique (Zelle dedupe); the import re-sorts the list, so list position can't be the key |
| `changelog` | `tracker_data.changelog` | `seq` | **insert-only** (trigger blocks update/delete, even for the owner) |
| `seen_emails` | `watch_state.seen` | `key` | |
| `app_state` | every other value: finance, ignore/watch senders, schema, generated, watch_state since/last_ok, brief files | (`doc`, `key`) | json value per top-level key |
| `settings` | prices, reply templates, privacy options (never in git) | `key` | |
| `private.app_users` | the login allowlist (user ID + label, no names) | `user_id` | schema not exposed by the API |
| Storage `contracts` | contract files (Phase 3) | path `leads/<id>/…` | private, 25 MB, PDF/DOCX/JSON only |

**Exact round trip (for Phase 3's "load() reproduces the JSON exactly"):**
- `pos` = position in the JSON list · `key_order` = the item's keys in order (a column whose key isn't listed was **missing**, not null) · `extra` = keys without a column, or values of the wrong type (e.g. a number in a text column).
- Nested JSON is `json`, not `jsonb` (jsonb re-sorts keys). Money is `numeric` and keeps `500.0` vs `500`.
- Defaults (`count` 1, `email_ids` []) only fill rows written outside the Python code (Stage 3 functions).

**Security:** RLS + FORCE RLS on every table. `anon`: no privileges at all. `authenticated`: SELECT only, and the policy requires `private.is_allowed()` (user ID on the allowlist). **No write policies**: the cloud stays read-only until Phase 7 (the Phase 4 server writes as the DB owner over the pooler). Default privileges revoked, so a future table is closed until granted on purpose.

**Not in v1 on purpose:** enum CHECKs and the alert→lead foreign key (the live data may hold values the code never wrote; added once Phase 3 proves the data clean) · outbox / heartbeat / job tables (Phase 4) · indexes beyond emails, status and lead_id.

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
| Changelog `old`/`new` and other nested data: `json`, not `jsonb` | ⏳ Proposed 11/10 (Claude). **Changed from v2's "jsonb"**: jsonb re-sorts keys, which fails Phase 3's exact test. Cast to jsonb when querying |
| Round-trip columns `pos`, `key_order`, `extra` on every list table | ⏳ Proposed 11/10 (Claude). Needed for exact missing-vs-null, key order and unknown keys |
| Storage test = "anon GET ≠ 200" instead of "= 403" | ⏳ Proposed 11/10 (Claude). Supabase answers 400/404 for private objects; what matters is no file |

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

## Status log
- 2026-11-10 — **Phase 2 drafted, not applied.** Taken over from Hermes by Claude (cloud session, branch `claude/gifted-dijkstra-maze19`; no access to the Mac, live JSON or Supabase from there). Migration + RLS + Storage written; columns built from every key the code reads/writes (server, watch, zelle_import, brief, calendar_sync, dashboard). Local tests on Postgres 16 with a Supabase stand-in: RLS/privilege test **80/80** (and a deliberately broken policy is caught: 8 fails); codec round trip **8/8**. Leak check 0 hits (generic only: live-data name check and gitleaks need the Mac). Waiting on: key profile from the live JSON, Ibrahim's approval, then apply + live test.
- 2026-11-10 — **Phase 1 passed.** Pushed `c325d31` to `main` (public). GitHub shows exactly the 18 files; local HEAD = remote HEAD; 0 secret-scanning alerts; pre-push leak check + gitleaks passed.
- 2026-11-10 — **Phase 1 prepared, not pushed.** Repo lives at `~/repos/ev-dashboard` (Ibrahim: never delete or move files in `~/EmanantHQ` or the vault; the repo holds COPIES of the code). Local commit `c325d31`, 18 files, authored as ibrahimmuzaffar10-ui (noreply). Addresses/prices moved to gitignored `.env.local` (loaded by `evenv.py`), contract wording loaded from `EV_CONTRACT_CONTENT_DIR`, data from `EV_DATA_DIR` (still `~/EmanantHQ`). Allowlist `.gitignore`; `scripts/check_leaks.py` + gitleaks in pre-commit/pre-push. Tests: leak check 0 hits on 18 files (373 live values + 190 name words); planted fake email/price and a real client name both blocked; repo copy on :8788 vs live :8787 byte-identical on /api/data, /api/brief, /calendar, /api/calendar, /docs/*; HTML identical except one 57-char allow comment; contract + questionnaire DOCX/PDF text identical (8/8, 5/5 pages). Awaiting Ibrahim's push approval.
- 2026-11-09 — **Phase 0 passed.** Supabase project `ev-dashboard` (org emanant-visuals, us-east-1) linked from `~/EmanantHQ/supabase/`. Sign-ups + email sign-ups off, anonymous off, min password 12; MFA (TOTP) and email confirmations kept ON (the default config.toml would have turned them off; local config aligned to remote first). Live probe: signup → 422 signup_disabled, anonymous → 422. Vercel region = `iad1` (next to us-east-1). Vercel Hobby team is single-user by design. GitHub non-provider secret patterns can't be enabled on this repo; standard scanning + push protection stay on.
- 2026-11-09 — Decisions applied: public repo with zero sensitive info, local outbox, no second backup, healthchecks.io alert.
- 2026-11-09 — v1 drafted. Two adversarial reviews run (technical + security); claims spot-checked against code and docs. v2 written.
