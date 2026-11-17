// All reads for the phone app: the signed-in user's own session through Row Level Security.
import "server-only";
import { connection } from "next/server";
import { supabaseServer } from "@/lib/supabase/server";
import { demo, demoAlerts, demoInst, demoLeads, demoPays, demoVendors } from "./demo";

export type Lead = {
  id: string; client: string; email: string | null; status: string; service: string | null; channel: string | null;
  inquiry: string | null; lastContact: string | null; eventText: string | null; venue: string | null;  // leak-check: allow: the app word "inquiry", not client data
  contract: string | null; retainer: string | null; balance: string | null; total: number | null; paid: number | null;
  notes: string | null; next: string | null; replied: string | null; gallery: string | null; review: string | null;
  lostReason: string | null; fault: string | null; call: string; callOn: string | null; callTime: string | null;
  days: { label: string | null; day: string | null; start: string | null; end: string | null; venue: string | null }[];
};
export type Alert = {
  id: string; at: string | null; type: string; title: string; detail: string; fromEmail: string | null;
  leadId: string | null; done: boolean; unread: boolean; count: number;
};
export type Installment = { leadId: string; index: number; label: string | null; due: string | null; amount: number; paid: boolean; paidOn: string | null };
export type Payment = { emailId: string; on: string | null; amount: number; sender: string | null; leadId: string | null; label: string | null; method: string | null };

// Houston "today"; waits for the request first (Next.js must not freeze the clock into a prerender)
export async function todayCT(): Promise<string> {
  await connection();
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/Chicago" }).format(new Date());
}

type Orig = { orig?: Record<string, unknown> } | null;
const extra = (s: Orig, k: string) => (s?.orig?.[k] as string | undefined) ?? null;

export async function loadLeads(): Promise<{ leads: Lead[]; error?: string }> {
  if (demo()) return { leads: demoLeads };
  await connection();
  const sb = await supabaseServer();
  const [l, c, d] = await Promise.all([
    sb.from("leads").select("lead_id, client_id, status, replied, gallery, review, lost_reason, fault, service, channel, inquiry_on, last_contact_on, event_text, venue, contract_status, retainer_status, balance_status, total, paid_manual, notes, action_note, legacy_shape"),  // leak-check: allow: the app word "inquiry", not client data
    sb.from("clients").select("client_id, name, email"),
    sb.from("event_days").select("lead_id, position, label, day, start_local, end_local, venue").order("position"),
  ]);
  const error = l.error?.message || c.error?.message || d.error?.message;
  if (error) return { leads: [], error };
  const cl = new Map((c.data || []).map((x) => [x.client_id, x]));
  const days = new Map<string, Lead["days"]>();
  for (const x of d.data || []) {
    const arr = days.get(x.lead_id) || [];
    arr.push({ label: x.label, day: x.day, start: x.start_local, end: x.end_local, venue: x.venue });
    days.set(x.lead_id, arr);
  }
  const leads = (l.data || []).map((x) => {
    const shape = x.legacy_shape as Orig;
    return {
      id: x.lead_id, client: cl.get(x.client_id)?.name || "(no name)", email: cl.get(x.client_id)?.email || null,
      status: x.status, service: x.service, channel: x.channel, inquiry: x.inquiry_on, lastContact: x.last_contact_on,  // leak-check: allow: the app word "inquiry", not client data
      eventText: x.event_text, venue: x.venue, contract: x.contract_status, retainer: x.retainer_status, balance: x.balance_status,
      total: x.total === null ? null : Number(x.total), paid: x.paid_manual === null ? null : Number(x.paid_manual),
      notes: x.notes, next: x.action_note, replied: x.replied, gallery: x.gallery, review: x.review, lostReason: x.lost_reason, fault: x.fault, call: extra(shape, "call") || "none", callOn: extra(shape, "call_on"), callTime: extra(shape, "call_time"),
      days: days.get(x.lead_id) || [],
    } satisfies Lead;
  });
  return { leads };
}

export async function loadAlerts(): Promise<{ alerts: Alert[]; error?: string }> {
  if (demo()) return { alerts: demoAlerts };
  await connection();
  const sb = await supabaseServer();
  const r = await sb.from("alerts").select("alert_id, at, type, title, detail, from_email, lead_id, done, unread, count").eq("done", false).order("at", { ascending: false });
  if (r.error) return { alerts: [], error: r.error.message };
  return {
    alerts: (r.data || []).map((x) => ({ id: x.alert_id, at: x.at, type: x.type, title: x.title || "", detail: x.detail || "",
      fromEmail: x.from_email, leadId: x.lead_id, done: x.done, unread: !!x.unread, count: x.count || 1 })),
  };
}

export async function loadMoney(): Promise<{ inst: Installment[]; pays: Payment[]; error?: string }> {
  if (demo()) return { inst: demoInst, pays: demoPays };
  await connection();
  const sb = await supabaseServer();
  const [i, p] = await Promise.all([
    sb.from("installments").select("lead_id, position, label, due_on, amount, paid, paid_on").order("due_on"),
    sb.from("payments").select("email_id, received_on, amount, sender, lead_id, client_label, method").order("received_on", { ascending: false }),
  ]);
  const error = i.error?.message || p.error?.message;
  return {
    inst: (i.data || []).map((x) => ({ leadId: x.lead_id, index: x.position, label: x.label, due: x.due_on, amount: Number(x.amount || 0), paid: !!x.paid, paidOn: x.paid_on })),
    pays: (p.data || []).map((x) => ({ emailId: x.email_id, on: x.received_on, amount: Number(x.amount || 0), sender: x.sender, leadId: x.lead_id, label: x.client_label, method: x.method })),
    error,
  };
}

export async function loadVendors() {
  if (demo()) return { vendors: demoVendors, error: undefined };
  await connection();
  const sb = await supabaseServer();
  const r = await sb.from("vendors").select("vendor_id, name, channel, type, note, follow").order("position");
  return { vendors: r.data || [], error: r.error?.message };
}

export async function loadHandled(): Promise<{ alerts: Alert[]; error?: string }> {
  if (demo()) return { alerts: [] };
  await connection();
  const sb = await supabaseServer();
  const r = await sb.from("alerts").select("alert_id, at, type, title, detail, from_email, lead_id, done, unread, count, ignored").eq("done", true).order("at", { ascending: false }).limit(30);
  if (r.error) return { alerts: [], error: r.error.message };
  return { alerts: (r.data || []).map((x) => ({ id: x.alert_id, at: x.at, type: x.type, title: (x.ignored ? "Not a lead · " : "") + (x.title || ""), detail: x.detail || "", fromEmail: x.from_email, leadId: x.lead_id, done: true, unread: false, count: x.count || 1 })) };
}

export type ContractPrefill = { fields: Record<string, string>; total: number | null; retainer: number | null; issued: string | null; signed: string | null } | null;
export async function loadContract(leadId: string): Promise<ContractPrefill> {
  if (demo()) return null;
  await connection();
  const sb = await supabaseServer();
  const r = await sb.from("contracts").select("fields, total, retainer, issued_on, signed_on").eq("lead_id", leadId).order("contract_id", { ascending: false }).limit(1);
  const c = r.data?.[0];
  return c ? { fields: (c.fields || {}) as Record<string, string>, total: c.total === null ? null : Number(c.total), retainer: c.retainer === null ? null : Number(c.retainer), issued: c.issued_on, signed: c.signed_on } : null;
}
