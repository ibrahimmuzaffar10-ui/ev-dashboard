# Moving the website off Vercel (if ever needed)

Everything Vercel runs for Emanant HQ, so it can be rebuilt on any other host. Only names are listed here;
the values live in Vercel's settings and in the Mac's gitignored `.env.local` (never in git).

## Why it might be needed (all unlikely)
- **Plan terms:** Vercel's free Hobby plan is meant for non-commercial use; a business dashboard is a grey
  area (accepted as a risk on 11/9). If Vercel ever enforces it, the choice is a paid plan or another host.
- **Free plan changes** (limits, pricing) or an **account problem** (locked login, billing).
- **An outage:** short ones need no move. Use the Mac copy at http://127.0.0.1:8787 (see `docs/OPERATIONS.md`).

Nothing about the data depends on Vercel: the data is in Supabase and the email jobs run on the Mac.

## What Vercel runs
| Piece | Where in the repo | Notes |
|---|---|---|
| One Python web function | `api/index.py` (wraps `server.py`) | Login (Supabase email + password + allowlist), then the same routes as the Mac server; Mac-only routes blocked |
| Files the function needs | `vercel.json` → `includeFiles` | server.py, db.py, legacy.py, mailer.py, docstore.py, evtime.py, evenv.py, both HTML pages, `supabase/supabase-ca.crt`, both contract renderers |
| Python packages | `requirements.txt` | pg8000, tzdata, python-docx, reportlab |
| Every URL → the function | `vercel.json` → `rewrites` | `/:path*` → `/api/index?__path=/:path*` (`api/index.py` restores the path) |
| Daily keep-alive | `vercel.json` → `crons` | `GET /api/_keepalive` at 12:00 UTC with `Authorization: Bearer <CRON_SECRET>`, so Supabase Free never pauses |
| Region | `vercel.json` → `regions` | `iad1` (US East), next to Supabase us-east-1 |
| Upload allowlist | `.vercelignore` | Only the files above are uploaded |
| Limits | `maxDuration` 30 s | Contract rendering is the slowest route |

## Settings (environment variables) on Vercel — names only
| Name | What it is |
|---|---|
| `SUPABASE_URL`, `SUPABASE_ANON_KEY` | Supabase project address + public key (login) |
| `EV_BACKEND` | `supabase` |
| `EV_DB_HOST`, `EV_DB_USER`, `EV_DB_PASSWORD` | Database login for the `ev_server` role (pooler host `aws-1-us-east-1…`, port 6543, TLS verified with the bundled CA) |
| `EV_CLOUD_WRITES` | `1` = saves allowed (rollback step R1 sets it to 0) |
| `EV_PRIVACY_OPTIONS`, `EV_OVERTIME_RATE` | Business settings shown in the dashboard |
| `EV_SELFTEST_TOKEN` | Secret header for `GET /api/_selftest` (renders a TEST contract) |
| `CRON_SECRET` | Secret for the keep-alive call |

## Moving to another host (checklist)
1. Pick a host that runs a Python 3.12+ web function or a small always-on Python process in a US-East region.
2. Upload only the `.vercelignore` allowlist files; install `requirements.txt`.
3. Serve every path through `api/index.py` (or run `server.py` behind the same login wrapper).
4. Copy the settings above (values from Vercel's dashboard or `.env.local`).
5. Recreate the daily keep-alive call with the same `CRON_SECRET` header.
6. Test: `GET /api/_selftest` with the `X-EV-Selftest` header → **200**; log in as Ibrahim → dashboard loads; a save without login → **401**.
7. In Supabase → Authentication → URL settings, set the site URL to the new address.
8. Only then remove the Vercel project.
