# CLAUDE.md — Emanant HQ (ev-dashboard)

Read this first, then `docs/ROADMAP.md` (the plan and the source of truth for status).

## What this is
Emanant HQ is the lead/booking/payment dashboard for Emanant Visuals, a two-person Houston wedding photography business: Eman (spelled E-m-a-n) shoots, Ibrahim (the user) runs the business. Today it runs **locally on Ibrahim's Mac** (Python stdlib server on `localhost:8787`, JSON files as the database). We are migrating it to **GitHub (this public repo) + Vercel Hobby (free) + Supabase Free**, phase by phase, per `docs/ROADMAP.md`. Mail/Zelle/brief/calendar syncs stay on the Mac permanently; a Next.js mobile-first rebuild comes later (Stage 3).

**Status:** Phase 0 ✅ (Supabase linked, sign-ups off) · Phase 1 ✅ (code in this repo, leak checks) · Phase 2 ✅ (schema v1; live test 92/92) · Phase 3 ✅ (data + 23 files copied, verified exact; Mac still live) · Phase 4a ✅ · **Live (read-only, login) at https://ev-dashboard-tan.vercel.app** · **Schema v2 normalized** (verify 15/15) · **Next: v2 save path, then 4b job routes, 4c outbox, 4d renderer/errors.**

## Hard rules (from Ibrahim — never break)
1. **Never delete or move existing files** in `~/EmanantHQ`, `~/Documents/Emanant Visuals`, or the Obsidian vault. Copy, don't move. Edits happen in this repo only. Scratch files you create yourself may be deleted (and must be, if they contain client data).
2. **Nothing sensitive in git, ever.** This repo is PUBLIC. No client names/emails/phones/notes/amounts, no personal or business email addresses, no phone numbers, no prices, no contract wording, no keys. Those go in Supabase (`settings` table / private Storage) or in gitignored `.env.local`.
3. **Don't touch the live system** (`~/EmanantHQ`, its launchd jobs, the running server on :8787) until the roadmap's cutover phase, and only after Ibrahim approves.
4. **Never ask for or accept passwords/keys in chat.** Never print the Supabase `service_role` key or any secret. Using the anon key is fine.
5. **Never push without Ibrahim's explicit "push".** Show him the staged file list + leak-check result first.
6. Don't send email, run the live sync scripts, or trigger real side effects (alerts, notifications, contract emails) while testing.

## How Ibrahim wants to work
- Compact, structured answers: tables, short bullets, no essays. Plain language (he's not a developer).
- Every phase has a **pass/fail test with a number**; report results as a table.
- **Keep him in the loop at each phase boundary**: show the plan/design before applying anything to Supabase/Vercel/GitHub, end with a short numbered "decisions needed" list.
- He types fast with typos: read for intent.
- If you change an earlier recommendation, say so and why, and update `docs/ROADMAP.md` in place (Decisions + Status log).
- Decisions already made (don't re-argue): public repo; Vercel **free** plan; syncs stay local on the Mac; email sending is local via an outbox (app password stays in the Mac Keychain); login = email + password for Ibrahim + Eman only (Ibrahim creates both users himself in the Supabase dashboard); no second backup copy; Mac-offline alert = healthchecks.io free; no dates, phase-gated.

## File map

### This repo — `~/repos/ev-dashboard`
| Path | What |
|---|---|
| `docs/ROADMAP.md` | The plan: stages, phases, pass/fail tests, schema notes, decisions, status log |
| `server.py` | Dashboard server (stdlib `ThreadingHTTPServer`; `load()`/`store()` on JSON; 6 GET + 13 POST routes) |
| `dashboard_template.html`, `calendar.html` | UI (single page; `__BOOT__` and `__PRIVACY_OPTIONS__` placeholders filled by the server) |
| `watch.py` | iCloud mail watcher (via `himalaya` CLI) → alerts; triggers `zelle_import.py` |
| `zelle_import.py`, `brief.py`, `calendar_sync.py` | Zelle payment import, twice-daily brief, iCloud calendar sync (AppleScript) |
| `contracts/render_contract.py`, `contracts/render_questionnaire.py` | DOCX/PDF renderers (python-docx + reportlab); contract wording is loaded from outside the repo |
| `db.py` | Data layer: `EV_BACKEND=json` (default, files) or `supabase` (one transaction + advisory lock per save, as role `ev_server` via the pooler, verified TLS) |
| `legacy.py` | Schema v2 ⇄ old JSON shape: one converter used by the import, the checker and the website (`legacy_shape` keeps absent keys / untypable originals) |
| `api/index.py`, `vercel.json`, `.vercelignore` | Vercel entry: server.py behind Supabase login + allowlist, read-only (403 on saves). `.vercelignore` is an allowlist |
| `mailer.py`, `outbox_send.py` | Email: one builder/sender; cloud mode queues in `outbox` (same transaction as the save), the Mac sender sends (never re-sends an interrupted email) |
| `scripts/test_step3.py` | Step 3 test: outbox, dry run (expect 13/13) |
| `docstore.py`, `docs_sync.py`, `scripts/load_files.py` | Contract files: `files` table + registry (cloud), Mac copy into Documents (never overwrites/deletes), loader for existing files + wording |
| `scripts/test_step4.py` | Step 4 test: contracts online (expect 14/14) |
| `deploy/launchd.py` | Installs/removes the Mac background jobs: `shadow` (step 5) or `prod` (cutover); keeps the originals |
| `scripts/shadow_compare.py` | Step 5: record the start, then compare shadow (Supabase) vs live after 48 h |
| `scripts/test_step2.py` | Step 2 test: watcher/Zelle/brief on Supabase in shadow mode, failure + retry + overlap + idempotency (expect 16/16); restores Supabase exactly |
| `scripts/migrate_v2.py`, `scripts/verify_v2.py` | Schema v2 import from a JSON snapshot (one transaction) and its exact check (expect 15/15) |
| `evtime.py` | Houston-time `now_ct()`/`today_ct()`: every date the app writes |
| `requirements.txt` | pg8000 + tzdata (repo `.venv` on the Mac; Vercel later) |
| `evenv.py` | Loads `.env.local` into `os.environ` (stdlib) |
| `.env.local` | **Gitignored.** Real addresses, prices, paths. Names documented in `.env.example` |
| `supabase/migrations/*.sql` | Schema migrations (v1 = Phase 2). Apply only after Ibrahim approves: `supabase db push` (dry run first) |
| `supabase/tests/rls_test.sql`, `supabase_stub.sql` | Local schema/RLS test on plain Postgres (stub mimics Supabase roles/auth/storage) |
| `supabase/tests/live_seed.sql`, `live_unseed.sql` | One TEST row per table for the live test, and its exact cleanup |
| `scripts/profile_keys.py` | Key names/types/counts of the live JSON vs the schema (prints no values) |
| `supabase/tests/rls_sim_live.sql` | Signed-in live test with stand-in users, fully rolled back (expect `RESULT 58 pass, 0 fail.`) |
| `scripts/migrate_data.py`, `scripts/verify_migration.py`, `scripts/migrate_files.py` | Phase 3: load a JSON snapshot (one transaction, re-runnable), prove the round trip exact, upload + SHA-verify contract files (manifest in `app_state`) |
| `scripts/test_rls_live.py` | Phase 2 live test with the anon key (needs the seed, a test PDF and two test logins in `.env.local`) |
| `supabase/supabase-ca.crt` | Supabase root CA certificates (public), from the installed CLI; used to verify the database connection |
| `scripts/set_server_password.py` | Sets/rotates the `ev_server` password straight into `.env.local` (never shown) |
| `scripts/test_phase4a.py` | Phase 4a test: cloud server = JSON server, parallel saves, folding deletes, CT dates, role limits, leaves Supabase unchanged (expect 19/19) |
| `supabase/config.toml` | Supabase CLI config, linked to the project (aligned with remote — see pitfalls) |
| `.gitignore` | **Allowlist**: everything ignored; a new file must be un-ignored on purpose |
| `scripts/check_leaks.py`, `.githooks/pre-commit`, `.githooks/pre-push`, `.gitleaks.toml` | Leak checks (run automatically; `core.hooksPath=.githooks` is set) |

### Live app (READ ONLY) — `~/EmanantHQ`
| Path | What |
|---|---|
| `tracker_data.json` | Main data: `leads` (116), `vendors` (40), `changelog` (270), `alerts` (28), `finance`, `ignore_senders`, `watch_senders`, `schema`, `generated` |
| `payments.json` (37), `watch_state.json` (873 seen), `brief_latest.json`, `brief_state.json`, `brief_ack.json` | Other data |
| `contracts/contract_final_content.py` | Contract wording + prices + payment details (sensitive; goes to private Storage in Phase 3) |
| `contracts/served/` | Blank VFinal contract + questionnaire (PDF/DOCX) |
| `contracts/pending/*.json` | 3 pending contract fills |
| `backups/` | 200 rolling `tracker_data` snapshots |
| `server.py`, `watch.py`, … | The originals the live system runs (the repo has edited copies) |
| `supabase/` | Duplicate of the repo's supabase folder from Phase 0; leave it |

### Other locations
| Path | What |
|---|---|
| `~/Documents/Emanant Visuals/` (`Contract Drafts/`, `Signed Contracts/`, `Questionnaires/`, `Contracts/`) | Generated client contracts (sensitive; to private Storage in Phase 3) |
| `~/Library/LaunchAgents/com.emanantvisuals.dashboard.plist`, `com.emanantvisuals.watch.plist` | Live server + 5-min watcher (launchd) |
| `~/.hermes/scripts/emanant_brief.sh`, `~/.hermes/scripts/emanant_calendar_sync.sh` | Wrappers that Hermes cron runs (brief hourly at :02, calendar every 30 min). Read-only reference until Phase 6 |
| `~/.hermes/skills/productivity/small-business-operations/references/contract-workflow.md` | Contract/questionnaire rules, render commands |
| `~/.hermes/skills/productivity/small-business-operations/SKILL.md` | Full business + dashboard context (lead fields, status codes, alert rules, pricing rules) |
| `~/Documents/Obsidian Vault/Projects/Emanant Visuals/Dashboard Spec.md` | Dashboard requirements (views, color code) |
| `~/Documents/Obsidian Vault/Decisions/Emanant HQ on free cloud stack.md` | Stack decision record |
| `~/.claude/skills/hormozi-growth-playbook/`, `~/.claude/skills/small-business-operations/` | Claude skills copied from Hermes 11/10 (Alex Hormozi growth playbook; business operations). Originals stay in `~/.hermes/skills/productivity/` and the vault's `Knowledge/Hormozi Playbook/` |
| `~/.hermes/venvs/ev/bin/python` | Python with python-docx, reportlab, pypdfium2 (renderers + render tests) |

## Accounts & tools (already set up on this Mac)
| Tool | State |
|---|---|
| GitHub `gh` | Active account `ibrahimmuzaffar10-ui` (repo owner, ADMIN). A second account `ibrahimmanagement26-sudo` is also in the keyring — if pushes fail, `gh auth switch -u ibrahimmuzaffar10-ui`. git HTTPS uses the gh credential helper. Commit author is set per-repo to `ibrahimmuzaffar10-ui` + GitHub noreply address |
| Supabase CLI (v2.121) | Logged in to org **emanant-visuals**; project `ev-dashboard`, ref `wpavksbquiqzqcnpacqf`, region **us-east-1**, linked from this repo's `supabase/`. Sign-ups + anonymous sign-ins **off**, min password 12, MFA (TOTP) + email confirmations **on** |
| Vercel CLI (v64) | Logged in as `ibrahimmanagement26-sudo`, team `photogrpahy-managment`, **Hobby**. Use region `iad1` (next to us-east-1). Repo is public, so the Hobby commit-author rule doesn't apply; Vercel's GitHub app must be given access to the `ibrahimmuzaffar10-ui` account in Phase 5 |
| `gitleaks` 8.30 | Installed (Homebrew) |

## How to test without touching the live app
1. Copy the data JSON files from `~/EmanantHQ` to a scratch folder (never move them).
2. Run the repo server on another port: `EV_DATA_DIR=<scratch> EV_DOCS_DIR=<scratch>/docs EV_PORT=8788 python3 server.py`.
3. Diff every GET (`/`, `/api/data`, `/api/brief`, `/calendar`, `/api/calendar`, `/docs/*`) against live `http://127.0.0.1:8787`.
4. Compare contract renders by DOCX text and PDF text/page count (pypdfium2), not bytes.
5. Use a TEST lead/alert for any write; never a real client.
6. Stop the test server and delete the scratch folder (it holds client data).

## Pitfalls already learned
- `supabase config push` with a fresh `supabase init` config.toml would **downgrade** remote auth (MFA off, confirmations off, site_url). Always run `supabase config diff`, align config.toml to remote, review, then `supabase config push --yes`.
- The Supabase connector/token can't list projects; use the CLI.
- Leak check false positives: mark the line `leak-check: allow: <reason>`; never weaken the checker to get a commit through.
- Live-code facts the schema/data layer must respect (from the adversarial review — details in `docs/ROADMAP.md`): `watch.py` marks emails seen **before** posting; IDs are `max+1` under a process-local `threading.LOCK`; `store()` must also write deletes (alert folding) and the changelog is insert-only; `brief.py`/`zelle_import.py`/`watch.py` write JSON files directly; optional keys are often **missing** (not null) and code relies on `.get(k, default)`; dates are text with `''` and nulls; Vercel's clock is UTC (use America/Chicago).
- The Supabase DB certificate is not in the Mac trust store: always pass `supabase/supabase-ca.crt`; never disable verification. The pooler host is `aws-1-us-east-1` (aws-0 says tenant not found).
- A role that writes the data tables needs EXECUTE on `private.j_text/j_num/j_bool` (generated columns).
- Schema v2: v1 raw tables live in schema `archive` (not exposed). `db.store()` refuses in cloud mode until the v2 save path is built; `test_phase4a.py` predates v2.
- Vercel rewrites send every request to `/api/index?__path=/<path>`; `api/index.py` restores the path.
- **This Mac's clock is America/New_York**; himalaya email dates are UTC. All writes go through `evtime` (Houston). Never use `datetime.now()`/`date.today()` for stored values.
- Mac jobs reach Supabase through `db.py` helpers (watcher/calendar via the local server's API; Zelle/brief/watch state directly). They need the repo `.venv` Python (pg8000) in cloud mode.
- macOS TCC: launchd jobs can't read `~/Documents` files they didn't create — keep job code outside `~/Documents`.
