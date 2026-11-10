# ev-dashboard

Emanant HQ: the lead, booking and payment dashboard for Emanant Visuals, moving from a local Mac app to GitHub + Vercel + Supabase.

**This repository is public and contains code only.** Client data, contact details, contract wording, prices and credentials are never committed:

| What | Where it lives |
|---|---|
| Leads, payments, alerts, changelog | Supabase database (local JSON files on the Mac until cutover) |
| Contract wording, signed contracts | Supabase private Storage (Mac folders until cutover) |
| Addresses, prices, paths | `.env.local` on the Mac (gitignored); setting names in `.env.example` |
| Mail password | macOS Keychain on the Mac only |

## Safety rails
- `.gitignore` is an **allowlist**: every file is ignored unless explicitly listed.
- `.githooks/pre-commit` and `.githooks/pre-push` run `scripts/check_leaks.py` (blocks emails, phone numbers, prices and any value found in the live data or `.env.local`) and `gitleaks`. Enable with `git config core.hooksPath .githooks`.

## Run locally
```
cp .env.example .env.local   # then fill in real values
python3 server.py            # http://localhost:8787 (EV_PORT to change)
```
Stdlib only, except contract rendering (python-docx, reportlab).
