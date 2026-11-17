"use client";
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { matchPayment } from "./actions";

export function Match({ emailId, leads }: { emailId: string; leads: { id: string; client: string }[] }) {
  const [open, setOpen] = useState(false);
  const [pick, setPick] = useState("");
  const [err, setErr] = useState("");
  const [pending, start] = useTransition();
  const router = useRouter();
  if (!open) return <button className="btn !min-h-8 !px-3 !py-1 text-[13px]" onClick={() => setOpen(true)}>Match</button>;
  return (
    <div className="mt-2 flex w-full gap-1.5">
      <select value={pick} onChange={(e) => setPick(e.target.value)} className="min-w-0 flex-1 rounded-lg border border-[var(--line)] bg-[var(--bg)] px-2 py-1.5 text-[14px]">
        <option value="">Which client?</option>{leads.map((l) => <option key={l.id} value={l.id}>{l.client}</option>)}
      </select>
      <button className="btn btn-primary !min-h-8 !px-3 !py-1 text-[13px]" disabled={!pick || pending}
              onClick={() => start(async () => { const r = await matchPayment(emailId, pick); if (r.ok) router.refresh(); else setErr(r.msg); })}>{pending ? "…" : "Save"}</button>
      {err && <span className="text-[12px] text-[var(--red)]">{err}</span>}
    </div>
  );
}
