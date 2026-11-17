"use server";
import { supabaseServer } from "@/lib/supabase/server";
import { oldApi } from "@/lib/bridge";

type Sub = { endpoint: string; keys: { p256dh: string; auth: string } };

// Saved with the user's own session: Row Level Security only lets them add/remove their own phone
export async function savePush(sub: Sub, device: string) {
  if (!sub?.endpoint?.startsWith("https://") || !sub.keys?.p256dh || !sub.keys?.auth) return { ok: false, msg: "Bad subscription" };
  const sb = await supabaseServer();
  await sb.from("push_subscriptions").delete().eq("endpoint", sub.endpoint);
  const { error } = await sb.from("push_subscriptions").insert({ endpoint: sub.endpoint, p256dh: sub.keys.p256dh, auth: sub.keys.auth, device: device.slice(0, 120) });
  return error ? { ok: false, msg: error.message } : { ok: true, msg: "Notifications on" };
}

export async function removePush(endpoint: string) {
  const sb = await supabaseServer();
  const { error } = await sb.from("push_subscriptions").delete().eq("endpoint", endpoint);
  return error ? { ok: false, msg: error.message } : { ok: true, msg: "Notifications off" };
}

export async function testPush() {
  try { await oldApi("/api/push-test", {}); return { ok: true, msg: "Test requested: the Mac sends it within a minute" }; }
  catch (e) { return { ok: false, msg: e instanceof Error ? e.message : "Failed" }; }
}
