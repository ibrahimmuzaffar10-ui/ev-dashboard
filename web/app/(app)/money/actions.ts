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

// "personal" = not business income · "other" = business income without a booking (e.g. second shooting) · null = back to "to match"
export async function setCategory(emailId: string, category: "personal" | "other" | null, note = "") {
  try { await oldApi("/api/payment-category", { email_id: emailId, category, note }); revalidatePath("/money"); revalidatePath("/money/progress");
        return { ok: true, msg: category === "personal" ? "Marked personal · not counted as business income" : category === "other" ? "Counted as business income (no booking)" : "Back in “To match”" }; }
  catch (e) { return { ok: false, msg: e instanceof Error ? e.message : "Not saved" }; }
}
