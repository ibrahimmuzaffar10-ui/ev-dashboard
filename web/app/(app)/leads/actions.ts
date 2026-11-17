"use server";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { oldApi } from "@/lib/bridge";

export type Result = { ok: boolean; msg: string };
const fail = (e: unknown): Result => ({ ok: false, msg: e instanceof Error ? e.message : "Not saved" });

// One field at a time, through the current dashboard's validation (same rules, same allowed values)
export async function updateField(id: string, field: string, value: string | number | null): Promise<Result> {
  try { await oldApi("/api/update", { id, field, value }); revalidatePath(`/leads/${id}`); return { ok: true, msg: "Saved" }; } catch (e) { return fail(e); }
}

export async function markReceived(id: string, index: number): Promise<Result> {
  try { await oldApi("/api/pay", { id, index }); revalidatePath(`/leads/${id}`); revalidatePath("/money"); return { ok: true, msg: "Marked received" }; } catch (e) { return fail(e); }
}

export type NewLeadState = { error?: string } | undefined;
export async function addLead(_: NewLeadState, form: FormData): Promise<NewLeadState> {
  const client = String(form.get("client") || "").trim();
  if (!client) return { error: "Enter the client's name" };
  const event = String(form.get("event") || "");
  let id = "";
  try {
    const r = await oldApi<{ lead: { id: string } }>("/api/add", {
      client, channel: String(form.get("channel") || ""), service: String(form.get("service") || "unknown"),
      src_email: String(form.get("email") || ""), notes: String(form.get("notes") || "").slice(0, 1000), ...(event ? { event } : {}),
    });
    id = r.lead.id;
  } catch (e) { return { error: e instanceof Error ? e.message : "Not added" }; }
  revalidatePath("/leads");
  redirect(`/leads/${id}`);
}
