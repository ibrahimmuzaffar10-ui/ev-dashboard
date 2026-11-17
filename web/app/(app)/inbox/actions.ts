"use server";
import { revalidatePath } from "next/cache";
import { oldApi } from "@/lib/bridge";

export type Result = { ok: boolean; msg: string };
const fail = (e: unknown): Result => ({ ok: false, msg: e instanceof Error ? e.message : "Something went wrong" });

export async function markDone(id: string): Promise<Result> {
  try { await oldApi("/api/alert", { id, action: "done" }); revalidatePath("/inbox"); return { ok: true, msg: "Marked handled" }; } catch (e) { return fail(e); }
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
