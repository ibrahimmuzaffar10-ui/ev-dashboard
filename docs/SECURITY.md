# Breach checklist — Emanant HQ

One page for "something is wrong": a lost Mac or phone, a login you didn't make, a key pasted somewhere public,
an email you didn't send. **Work top to bottom. Speed beats perfection: lock first, investigate second.**
No secret values live in this file; it names *where* each one is and *how* to replace it.

## 1. Lock it down (first 15 minutes)

| Do this | How | What it stops |
|---|---|---|
| Change both login passwords (**before** the kill switch: the script only works for allowlisted accounts) | `.venv/bin/python scripts/set_login_password.py` (hidden prompt) for each user, or Supabase → Authentication → Users | A stolen password |
| **Kill switch: empty the login allowlist** | Supabase dashboard → SQL editor: `delete from private.app_users;` (or ask Claude). Re-add each person later | Both apps (phone + old site) instantly show **no data** to anyone, even with a valid login |
| Sign everyone out | Supabase → Authentication → Users → each user → sign out / ban for a while | Sessions already open on a stolen phone or laptop |
| Stop the Mac jobs (only if the **Mac** is the problem) | `python3 deploy/launchd.py prod remove` (keeps the files; reinstall with `install`) | Email sending, Zelle/mail reading from that Mac |
| Revoke the iCloud **app password** (if the Mac or the mail account is involved) | appleid.apple.com → Sign-In and Security → App-Specific Passwords → revoke. New one → Mac Keychain item `hermes-icloud` | Anyone reading or sending Eman's business mail with it |

## 2. Replace every key that could be exposed

| Secret | Lives in | Replace it by |
|---|---|---|
| Database role password (`EV_DB_PASSWORD`) | Mac `.env.local` + old Vercel project env | `python3 scripts/set_server_password.py` → update the Vercel env var → redeploy → `launchctl kickstart -k gui/$UID/com.emanantvisuals.dashboard` |
| Mac job token (`EV_JOB_TOKEN`) | Mac `.env.local` + old Vercel project env | New random value in both → redeploy → restart the Mac jobs |
| Vercel cron + self-test secrets (`CRON_SECRET`, `EV_SELFTEST_TOKEN`) | Old Vercel project env | New random values → redeploy |
| Supabase anon key (`SUPABASE_ANON_KEY`) | Both Vercel projects + `.env.local` | Supabase → Project Settings → API keys → rotate → update all three → redeploy both. (Low risk alone: RLS + the allowlist still apply) |
| Supabase admin key (service_role) | Supabase dashboard only, **never stored by the app** | Rotate in the dashboard if it was ever copied anywhere |
| Push key (`EV_VAPID_PRIVATE_KEY`) | Mac `.env.local` only | New key pair → web `VAPID_PUBLIC_KEY` → redeploy → each phone turns notifications off/on |
| Healthcheck URLs | Mac `.env.local` | healthchecks.io → check → regenerate URL |
| Account logins: Supabase, Vercel, GitHub, Apple ID | Password manager | Change password, check 2-step login is on, sign out other sessions |

A key pasted into GitHub: **rotate it first**, then remove it. Deleting the commit alone is not enough (forks and caches keep it).

## 3. Find out what happened

- **Supabase** → Authentication → Logs: sign-ins (time, IP). Logs → API / Postgres: unusual reads or writes.
- **Vercel** → each project → Logs: requests around the time.
- **Mac outbox**: emails sent (Money/Inbox history, or ask Claude to list the `outbox` table).
- **GitHub** → repo → Security → secret scanning alerts; `git log` for unexpected commits.
- Restore anything changed from the newest good backup (`scripts/backup.py`, 30 kept; see `docs/OPERATIONS.md`).

## 4. Decide on telling clients (with a professional)

What the app holds: client names, emails, phones, event dates/venues, notes, payment amounts and contracts.
It holds **no** card numbers, bank account numbers or SSNs.
Texas law (Bus. & Com. Code §521.053) requires notifying affected people when "sensitive personal information"
(e.g. a name together with an SSN, driver's license or financial account number) is exposed, within 60 days, and
the Texas Attorney General when 250+ Texans are affected. Most Emanant data likely falls outside that definition,
but **this is not legal advice: confirm with an attorney before deciding**. When in doubt, a short honest note to
affected clients protects trust more than silence.

## 5. Afterwards

- Write one line in `docs/ROADMAP.md` (status log): what happened, what was rotated, what changed.
- Re-add people to the allowlist (Claude can do it) and confirm both apps load.
- Run the leak check (`python3 scripts/check_leaks.py`) and the backup drill (`scripts/restore_drill.py`).
