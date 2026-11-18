"use server";
import { revalidatePath } from "next/cache";
import { oldApi, oldGet } from "@/lib/bridge";

export type Result = { ok: boolean; msg: string };
const fail = (e: unknown): Result => ({ ok: false, msg: e instanceof Error ? e.message : "Something went wrong" });

// refresh=false keeps the card on screen showing "Moved to Handled · Undo" (the Inbox refreshes on its own later)
export async function markDone(id: string, refresh = true): Promise<Result> {
  try { await oldApi("/api/alert", { id, action: "done" }); if (refresh) revalidatePath("/inbox"); return { ok: true, msg: "Marked handled" }; } catch (e) { return fail(e); }
}

export async function notALead(id: string): Promise<Result> {
  try { await oldApi("/api/alert", { id, action: "ignore" }); revalidatePath("/inbox"); return { ok: true, msg: "Hidden · future emails from this sender won't alert" }; } catch (e) { return fail(e); }
}

export async function addAsLead(id: string, client: string, notes: string, event: string, email: string | null): Promise<Result> {
  try {
    const today = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Chicago" }).format(new Date());
    const r = await oldApi<{ lead: { id: string } }>("/api/add", { client, channel: "Email", inquiry: today, notes: notes.slice(0, 1000), src_email: email || "", ...(event ? { event } : {}) });  // leak-check: allow: the app word "inquiry", not client data
    await oldApi("/api/alert", { id, action: "done", lead_id: r.lead.id });
    revalidatePath("/inbox"); revalidatePath("/leads");
    return { ok: true, msg: `Added ${client} as a lead` };
  } catch (e) { return fail(e); }
}

export async function sendReply(id: string, subject: string, body: string, callOffer: boolean): Promise<Result> {
  try {
    if (body.includes("[Pick one")) return { ok: false, msg: "Pick one of the [ ] options first" };
    await oldApi("/api/send-reply", { id, subject, body, call_offer: callOffer });
    revalidatePath("/inbox");
    return { ok: true, msg: "Sent · it goes out from Eman's email within a minute (when the Mac is on)" };
  } catch (e) { return fail(e); }
}

export async function checkNow(): Promise<{ ok: boolean; requested?: string; msg?: string }> {
  try { const r = await oldApi<{ requested: string }>("/api/check-now", {}); return { ok: true, requested: r.requested }; } catch (e) { return { ok: false, msg: fail(e).msg }; }
}

export async function lastCheck(): Promise<string | null> {
  const d = await oldGet<{ watcher_at?: string }>("/api/outbox");
  return d?.watcher_at || null;
}

export async function outboxAction(id: number, action: "cancel" | "retry"): Promise<Result> {
  try { await oldApi("/api/outbox-action", { id, action }); revalidatePath("/inbox"); return { ok: true, msg: action === "retry" ? "Queued to send" : "Cancelled" }; } catch (e) { return fail(e); }
}

export async function reopen(id: string, refresh = true): Promise<Result> {
  try { await oldApi("/api/alert", { id, action: "undo" }); if (refresh) revalidatePath("/inbox"); return { ok: true, msg: "Reopened" }; } catch (e) { return fail(e); }
}

// For now (Ibrahim 11/18) replies go to Eman's own inbox as a draft; she reviews it and sends it to the client herself.
export async function draftToEman(id: string, subject: string, body: string): Promise<Result> {
  try { await oldApi("/api/draft-to-eman", { id, subject, body }); return { ok: true, msg: "Draft emailed to Eman. Nothing was sent to the client" }; } catch (e) { return fail(e); }
}
