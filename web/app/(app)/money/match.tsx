"use client";
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { applyPayment, setCategory } from "./actions";

export type Owing = { id: string; label: string };

// Only bookings that still owe money are listed; a booking leaves the list once it is paid in full.
export function Match({ emailId, owing }: { emailId: string; owing: Owing[] }) {
  const [open, setOpen] = useState(false);
  const [pick, setPick] = useState("");
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; msg: string } | null>(null);
  const [pending, start] = useTransition();
  const router = useRouter();
  if (msg?.ok) return <p className="mt-2 w-full text-[13px]" style={{ color: "var(--green)" }}>✓ {msg.msg}</p>;
  if (!open) return <button className="btn btn-primary !min-h-8 !px-3 !py-1 text-[13px]" onClick={() => setOpen(true)}>Match</button>;
  return (
    <div className="mt-2 w-full space-y-1.5">
      <select value={pick} onChange={(e) => setPick(e.target.value)} className="w-full rounded-lg border border-[var(--line)] bg-[var(--bg)] px-2.5 py-2 text-[14px]">
        <option value="">Which booking is this payment for?</option>
        {owing.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
      </select>
      <div className="flex gap-1.5">
        <button className="btn btn-primary flex-1" disabled={!pick || pending}
                onClick={() => start(async () => { const r = await applyPayment(emailId, pick); setMsg(r); if (r.ok) setTimeout(() => router.refresh(), 2500); })}>
          {pending ? "Applying…" : "Apply payment"}
        </button>
        <button className="btn" onClick={() => { setOpen(false); setMsg(null); }}>Cancel</button>
      </div>
      <div className="pt-1 text-[12px] text-[var(--muted)]">Not for a booking?</div>
      <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (optional), e.g. 2nd shooting for another photographer"
             className="w-full rounded-lg border border-[var(--line)] bg-[var(--bg)] px-2.5 py-2 text-[14px]" />
      <div className="flex gap-1.5">
        <button className="btn flex-1" disabled={pending}
                onClick={() => start(async () => { const r = await setCategory(emailId, "other", note); setMsg(r); if (r.ok) setTimeout(() => router.refresh(), 1500); })}>
          Business, no booking
        </button>
        <button className="btn flex-1" disabled={pending}
                onClick={() => start(async () => { const r = await setCategory(emailId, "personal", note); setMsg(r); if (r.ok) setTimeout(() => router.refresh(), 1500); })}>
          Personal
        </button>
      </div>
      {msg && !msg.ok && <p className="text-[12px] text-[var(--red)]">{msg.msg}</p>}
      {!owing.length && <p className="text-[12px] text-[var(--muted)]">No booking has money left to pay.</p>}
    </div>
  );
}

// Undo a "personal" / "business, no booking" choice: the payment goes back to "To match"
export function Unsort({ emailId }: { emailId: string }) {
  const [done, setDone] = useState("");
  const [pending, start] = useTransition();
  const router = useRouter();
  if (done) return <span className="text-[12px]" style={{ color: "var(--green)" }}>{done}</span>;
  return <button className="btn !min-h-8 !px-3 !py-1 text-[13px]" disabled={pending}
                 onClick={() => start(async () => { const r = await setCategory(emailId, null); setDone(r.ok ? "✓ Back to To match" : r.msg); if (r.ok) setTimeout(() => router.refresh(), 1200); })}>Undo</button>;
}
