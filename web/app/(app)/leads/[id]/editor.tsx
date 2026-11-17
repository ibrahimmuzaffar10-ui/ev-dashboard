"use client";
import { useState, useTransition } from "react";
import type { Lead } from "@/lib/data";
import { updateField, type Result } from "../actions";

type Opt = [string, string];
export const OPTS: Record<string, Opt[]> = {
  status: [["unanswered", "Needs reply"], ["open", "Waiting on client"], ["booked", "Booked"], ["completed", "Completed"], ["ghosted", "Ghosted"], ["lost", "Lost"]],
  replied: [["yes", "Yes"], ["no", "No"]],
  call: [["none", "Not offered"], ["offered", "Offered"], ["booked", "Booked"], ["done", "Done"], ["declined", "Declined"]],
  contract: [["not_sent", "Not sent"], ["sent", "Sent"], ["signed", "Signed"], ["unknown", "Unknown"], ["n/a", "N/A"]],
  retainer: [["unpaid", "Unpaid"], ["partial", "Partly paid"], ["paid", "Paid"], ["unknown", "Unknown"], ["n/a", "N/A"]],
  balance: [["due", "Due"], ["partial", "Partly paid"], ["paid_in_full", "Paid in full"], ["unknown", "Unknown"], ["n/a", "N/A"]],
  gallery: [["no", "Pending"], ["yes", "Delivered"], ["unknown", "Unknown"], ["n/a", "N/A"]],
  review: [["none", "Not asked"], ["requested", "Requested"], ["received", "Received"]],
  lost_reason: [["", "— pick a reason —"], ["went_with_other", "Went with another photographer"], ["price", "Price / budget"], ["client_ghosted", "Client stopped replying"],
    ["changed_plans", "Plans changed / cancelled"], ["date_conflict", "Date conflict (already booked)"], ["date_passed", "Event date passed"], ["travel", "Eman traveling that date"],
    ["no_reply_us", "We replied too late / not at all"], ["service_gap", "Wanted something we don't offer"], ["other", "Other"]],
  fault: [["unknown", "Not sure"], ["client", "Client side"], ["ours", "Our side"], ["timing", "No fault · bad timing"]],
};
const FAULT_OF: Record<string, string> = { went_with_other: "client", price: "client", client_ghosted: "client", changed_plans: "client", date_conflict: "timing", date_passed: "timing", travel: "ours", no_reply_us: "ours", service_gap: "ours", other: "unknown" };

const input = "w-full rounded-xl border border-[var(--line)] bg-[var(--bg)] px-3 py-2.5 text-[15px]";

export function Editor({ lead }: { lead: Lead }) {
  const [v, setV] = useState<Record<string, string>>({
    status: lead.status, replied: lead.replied || "no", call: lead.call, contract: lead.contract || "n/a", retainer: lead.retainer || "n/a",
    balance: lead.balance || "n/a", gallery: lead.gallery || "n/a", review: lead.review || "none", lost_reason: lead.lostReason || "", fault: lead.fault || "unknown",
    event: lead.days.length === 1 || !lead.days.length ? lead.days[0]?.day || "" : "", call_on: lead.callOn || "", call_time: lead.callTime || "",
    total: lead.total?.toString() || "", paid: lead.paid?.toString() || "", action_note: lead.next || "", notes: lead.notes || "",
  });
  const [msg, setMsg] = useState<Result | null>(null);
  const [pending, start] = useTransition();
  const save = (field: string, value: string) => {
    const before = v[field];
    setV((x) => ({ ...x, [field]: value }));
    start(async () => {
      const send = ["total", "paid"].includes(field) ? (value.replace(/[$,\s]/g, "") === "" ? null : Number(value.replace(/[$,\s]/g, ""))) : value;
      if (typeof send === "number" && Number.isNaN(send)) { setMsg({ ok: false, msg: "Enter a number" }); setV((x) => ({ ...x, [field]: before })); return; }
      const r = await updateField(lead.id, field, send);
      setMsg(r);
      if (!r.ok) setV((x) => ({ ...x, [field]: before }));
      else if (field === "lost_reason" && FAULT_OF[value] && v.fault === "unknown") save("fault", FAULT_OF[value]);
    });
  };
  const sel = (f: string, label: string) => (
    <label className="flex items-center justify-between gap-3 px-4 py-2.5">
      <span className="text-[var(--muted)]">{label}</span>
      <select value={v[f]} onChange={(e) => save(f, e.target.value)} className="max-w-[60%] rounded-lg border border-[var(--line)] bg-[var(--bg)] px-2.5 py-2 text-[15px]">
        {OPTS[f].filter(([k]) => k || f === "lost_reason").map(([k, l]) => <option key={k} value={k}>{l}</option>)}
      </select>
    </label>
  );
  const text = (f: string, label: string, type = "text", ph = "") => (
    <label className="block px-4 py-2.5">
      <span className="text-sm text-[var(--muted)]">{label}</span>
      {type === "area"
        ? <textarea defaultValue={v[f]} rows={3} placeholder={ph} onBlur={(e) => e.target.value !== v[f] && save(f, e.target.value)} className={input + " mt-1"} />
        : <input type={type} defaultValue={v[f]} placeholder={ph} inputMode={type === "money" ? "decimal" : undefined}
                 onBlur={(e) => e.target.value !== v[f] && save(f, e.target.value)} onChange={(e) => type === "date" && save(f, e.target.value)} className={input + " mt-1"} />}
    </label>
  );
  return (
    <div className="space-y-4">
      <div className="card divide-y divide-[var(--line)]">
        {sel("status", "Status")}
        {v.status === "lost" || v.status === "ghosted" ? <>{sel("lost_reason", "Why")}{sel("fault", "Whose side")}</> : null}
        {sel("replied", "We replied")}
      </div>
      <div className="card divide-y divide-[var(--line)]">
        {sel("call", "15-min call")}
        {["offered", "booked", "done"].includes(v.call) && <div className="grid grid-cols-2">{text("call_on", "Call date", "date")}{text("call_time", "Time", "text", "6:30 PM")}</div>}
      </div>
      <div className="card divide-y divide-[var(--line)]">
        {sel("contract", "Contract")}{sel("retainer", "Retainer")}{sel("balance", "Balance")}
        <div className="grid grid-cols-2">{text("total", "Total ($)", "money")}{text("paid", "Paid so far ($)", "money")}</div>
        {sel("gallery", "Gallery")}{sel("review", "Review")}
      </div>
      <div className="card divide-y divide-[var(--line)]">
        {lead.days.length <= 1 ? text("event", "Event date", "date") : <p className="px-4 py-3 text-sm text-[var(--muted)]">Several event days come from the contract.</p>}
        {text("action_note", "Next step", "text", "e.g. Send the questionnaire")}
        {text("notes", "Notes", "area")}
      </div>
      <p role="status" aria-live="polite" className="h-5 text-center text-[13px]" style={{ color: msg?.ok ? "var(--green)" : "var(--red)" }}>
        {pending ? "Saving…" : msg ? (msg.ok ? "✓ " : "Not saved: ") + msg.msg : ""}
      </p>
    </div>
  );
}
