# Emanant HQ — phone-first app (Stage 3)

Next.js (App Router, TypeScript, Tailwind) on the same Supabase project as the current dashboard.
Plan and pass/fail tests: `../docs/ROADMAP.md` (phases 12–18).

- Login: Supabase email + password; only allowlisted accounts see data (Row Level Security).
- Reads use the signed-in user's own session: no service/admin key anywhere in `web/`.
- Settings (server-only, never sent to the browser): `SUPABASE_URL`, `SUPABASE_ANON_KEY` in `web/.env.local` / Vercel (type secret).
- Own Vercel project (deploy from `web/`), region `iad1`.

`npm run dev` · `npm run build` · read `AGENTS.md` first (this Next.js version differs from older docs).
