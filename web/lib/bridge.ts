// Saves go through the current dashboard's proven routes (one copy of the business rules until Phase 14),
// called server-to-server with the signed-in user's own Supabase token. The old site checks the token and
// the allowlist itself. No extra keys.
import "server-only";
import { supabaseServer } from "@/lib/supabase/server";

const OLD = process.env.EV_OLD_API || "https://ev-dashboard-tan.vercel.app";

export async function oldApi<T = unknown>(path: string, body: unknown): Promise<T> {
  const sb = await supabaseServer();
  const { data: { session } } = await sb.auth.getSession();
  if (!session) throw new Error("Signed out: sign in again");
  const r = await fetch(OLD + path, {
    method: "POST", cache: "no-store",
    headers: { "Content-Type": "application/json", Cookie: `ev_at=${session.access_token}` },
    body: JSON.stringify(body),
  });
  const text = await r.text();
  if (!r.ok) throw new Error(text.slice(0, 160) || `HTTP ${r.status}`);
  return (text ? JSON.parse(text) : {}) as T;
}

export async function oldGet<T = unknown>(path: string): Promise<T | null> {
  const sb = await supabaseServer();
  const { data: { session } } = await sb.auth.getSession();
  if (!session) return null;
  try {
    const r = await fetch(OLD + path, { cache: "no-store", headers: { Cookie: `ev_at=${session.access_token}` } });
    return r.ok ? ((await r.json()) as T) : null;
  } catch { return null; }
}
