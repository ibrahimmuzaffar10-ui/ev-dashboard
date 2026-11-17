"use client";
import { useState, useTransition } from "react";
import { checkNow, lastCheck, outboxAction } from "./actions";

export type Health = { mac_online: boolean; watcher_minutes_ago: number | null; emails_waiting: number } | null;
export type OutRow = { id: number; to: string; subject: string; status: string; error: string | null; queued: string };

const ago = (m: number | null) => m === null ? "a while" : m < 60 ? `${m} min` : m < 48 * 60 ? `${Math.round(m / 60)} h` : `${Math.round(m / 1440)} days`;
const LABEL: Record<string, string> = { queued: "Waiting", sending: "Sending", failed: "Not sent", unknown: "Check Sent folder", cancelled: "Cancelled" };

export function MacStatus({ health, rows }: { health: Health; rows: OutRow[] }) {
  const [state, setState] = useState<string>("");
  const [pending, start] = useTransition();
  const [hidden, setHidden] = useState<number[]>([]);
  const check = () => start(async () => {
    setState("Asking the Mac to check…");
    const r = await checkNow();
    if (!r.ok) { setState("Couldn't ask: " + r.msg); return; }
    for (let i = 0; i < 16; i++) {
      await new Promise((z) => setTimeout(z, 15000));
      const at = await lastCheck();
      if (at && r.requested && at >= r.requested) { setState("✓ Checked just now"); location.reload(); return; }
    }
    setState("The Mac hasn't checked yet: it will as soon as it's on and online.");
  });
  const live = rows.filter((r) => !hidden.includes(r.id) && r.status !== "cancelled");
  return (
    <div className="mt-3 space-y-2">
      {health && !health.mac_online && (
        <div className="rounded-2xl px-4 py-3 text-[14px]" style={{ background: "var(--red-bg)", color: "var(--red)" }}>
          💻 Mac offline · last email check {ago(health.watcher_minutes_ago)} ago. New emails and Zelle payments show up once it&apos;s back online. Edits here still save.
        </div>
      )}
      <div className="flex items-center gap-3">
        <button onClick={check} disabled={pending} className="btn">🔄 {pending ? "Checking…" : "Check email now"}</button>
        <span className="text-[13px] text-[var(--muted)]">{state || (health ? `Last check ${ago(health.watcher_minutes_ago)} ago` : "")}</span>
      </div>
      {live.length > 0 && (
        <div className="rounded-2xl px-4 py-3 text-[14px]" style={{ background: "var(--amber-bg)", color: "var(--amber)" }}>
          <div className="font-semibold">✉️ {live.length} email{live.length > 1 ? "s" : ""} waiting to send</div>
          <ul className="mt-1 space-y-2">
            {live.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-2">
                <span className="min-w-0 flex-1 truncate">{LABEL[r.status] || r.status} · {r.subject}{r.error ? ` · ${r.error}` : ""}</span>
                {["queued", "failed", "unknown"].includes(r.status) && <button className="btn !min-h-8 !px-3 !py-1 text-[13px]" onClick={() => start(async () => { const x = await outboxAction(r.id, "cancel"); if (x.ok) setHidden((h) => [...h, r.id]); })}>Cancel</button>}
                {["failed", "unknown"].includes(r.status) && <button className="btn btn-primary !min-h-8 !px-3 !py-1 text-[13px]" onClick={() => confirm("Send this email again? Only if it's still correct and NOT already in Eman's Sent folder.") && start(async () => { await outboxAction(r.id, "retry"); })}>Send again</button>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
