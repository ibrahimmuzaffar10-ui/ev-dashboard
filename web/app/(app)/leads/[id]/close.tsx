"use client";
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { closeLead, reopenLead, type Result } from "../actions";
import { OPTS, FAULT_OF } from "@/lib/lead-options";

// Bottom of a lead: "Close this lead" → pick why → confirm. Nothing is deleted; it moves to the Lost tab and can be reopened.
export function CloseLead({ id, status, notes, suggest, why, stamp }: { id: string; status: string; notes: string; suggest: string; why: string | null; stamp: string }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState(suggest);
  const [fault, setFault] = useState(FAULT_OF[suggest] || "unknown");
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<Result | null>(null);
  const [pending, start] = useTransition();
  const router = useRouter();
  const closed = status === "lost" || status === "ghosted";
  if (msg?.ok) return <p className="card mt-6 px-4 py-3 text-center text-[14px]" style={{ color: "var(--green)" }}>✓ {msg.msg}</p>;

  if (closed) return (
    <div className="card mt-6 flex items-center justify-between gap-3 px-4 py-3">
      <div className="min-w-0 text-[14px]"><div className="font-medium">Closed{why ? ` · ${why}` : ""}</div><div className="text-[12px] text-[var(--muted)]">Kept in the Lost tab with all its details.</div></div>
      <button className="btn shrink-0" disabled={pending} onClick={() => start(async () => { const r = await reopenLead(id, notes, stamp); setMsg(r); if (r.ok) router.refresh(); })}>{pending ? "…" : "Reopen"}</button>
    </div>
  );
  if (!open) return <button className="btn mt-6 w-full" style={{ color: "var(--red)" }} onClick={() => setOpen(true)}>Close this lead (lost / no longer waiting)…</button>;

  return (
    <div className="card mt-6 p-4">
      <div className="font-semibold">Close this lead</div>
      <p className="mt-0.5 text-[13px] text-[var(--muted)]">Nothing is deleted. It moves to the Lost tab, keeps all its details, and you can reopen it any time.</p>
      <div className="mt-3 text-[13px] font-medium text-[var(--muted)]">Why?</div>
      <div className="mt-1 space-y-1">
        {OPTS.lost_reason.filter(([k]) => k).map(([k, l]) => (
          <label key={k} className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-[15px]" style={reason === k ? { background: "var(--accent-soft)" } : undefined}>
            <input type="radio" name={`why-${id}`} checked={reason === k} onChange={() => { setReason(k); setFault(FAULT_OF[k] || "unknown"); }} /> {l}
          </label>
        ))}
      </div>
      <label className="mt-3 flex items-center justify-between gap-3 text-[14px]">
        <span className="text-[var(--muted)]">Whose side</span>
        <select value={fault} onChange={(e) => setFault(e.target.value)} className="rounded-lg border border-[var(--line)] bg-[var(--bg)] px-2.5 py-2 text-[15px]">
          {OPTS.fault.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
      </label>
      <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (optional), e.g. booked someone local"
             className="mt-3 w-full rounded-lg border border-[var(--line)] bg-[var(--bg)] px-2.5 py-2 text-[15px]" />
      <div className="mt-3 flex gap-2">
        <button className="btn flex-1 font-semibold" style={{ background: "var(--red)", color: "#fff", borderColor: "var(--red)" }} disabled={!reason || pending}
                onClick={() => start(async () => { const r = await closeLead(id, reason, fault, note, notes, stamp); setMsg(r); if (r.ok) router.refresh(); })}>
          {pending ? "Closing…" : reason === "client_ghosted" ? "Confirm · mark ghosted" : "Confirm · mark lost"}
        </button>
        <button className="btn" disabled={pending} onClick={() => setOpen(false)}>Cancel</button>
      </div>
      {msg && !msg.ok && <p className="mt-2 text-[13px]" style={{ color: "var(--red)" }}>Not saved: {msg.msg}</p>}
    </div>
  );
}
