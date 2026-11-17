"use server";
import { revalidatePath } from "next/cache";
import { oldApi } from "@/lib/bridge";

export async function matchPayment(emailId: string, leadId: string | null) {
  try { await oldApi("/api/payment-match", { email_id: emailId, lead_id: leadId }); revalidatePath("/money"); return { ok: true, msg: leadId ? "Matched" : "Unmatched" }; }
  catch (e) { return { ok: false, msg: e instanceof Error ? e.message : "Not saved" }; }
}
