"use server";
import { supabaseServer } from "@/lib/supabase/server";

// A few bytes: latest change time of alerts, leads and payments + open alert count. The page refreshes only when it moves.
export async function version(): Promise<string> {
  const sb = await supabaseServer();
  const last = (t: string) => sb.from(t).select("updated_at").order("updated_at", { ascending: false }).limit(1);
  const [a, l, p, n] = await Promise.all([last("alerts"), last("leads"), last("payments"), sb.from("alerts").select("alert_id", { count: "exact", head: true }).eq("done", false)]);
  return [a.data?.[0]?.updated_at, l.data?.[0]?.updated_at, p.data?.[0]?.updated_at, n.count].join("|");
}
