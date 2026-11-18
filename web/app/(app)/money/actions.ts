"use server";
import { revalidatePath } from "next/cache";
import { oldApi } from "@/lib/bridge";

// Credit one Zelle (from anyone: parent, sibling, in-law…) to the booking it is for. The server applies it to the
// oldest unpaid installments, splits a partial one, and refuses to apply the same payment twice.
export async function applyPayment(emailId: string, leadId: string) {
  try {
    const r = await oldApi<{ applied: string[]; left: number | null; client: string }>("/api/payment-apply", { email_id: emailId, lead_id: leadId });
    revalidatePath("/money"); revalidatePath(`/leads/${leadId}`);
    const left = r.left === null ? "" : r.left > 0 ? ` · $${r.left.toLocaleString("en-US")} still owed` : " · paid in full 🎉";
    return { ok: true, msg: `${r.client}: ${r.applied.join(", ")}${left}` };
  } catch (e) { return { ok: false, msg: e instanceof Error ? e.message : "Not saved" }; }
}

export async function setPersonal(emailId: string, personal: boolean) {
  try { await oldApi("/api/payment-personal", { email_id: emailId, personal }); revalidatePath("/money"); revalidatePath("/money/progress");
        return { ok: true, msg: personal ? "Marked personal · not counted as business income" : "Moved back to business" }; }
  catch (e) { return { ok: false, msg: e instanceof Error ? e.message : "Not saved" }; }
}
