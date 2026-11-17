"use client";
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { schedule, type Result } from "../actions";
import { PayButton } from "./pay-button";

type Item = { index: number; label: string | null; due: string | null; amount: number; paid: boolean; paidOn: string | null; overdue: boolean; dueText: string };
const box = "w-full rounded-lg border border-[var(--line)] bg-[var(--bg)] px-2.5 py-2 text-[14px] text-[var(--ink)]";
const fmt = (n: number) => n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

function Form({ id, item, onDone }: { id: string; item?: Item; onDone: () => void }) {
  const [label, setLabel] = useState(item?.label || "");
  const [amount, setAmount] = useState(item ? String(item.amount) : "");
  const [due, setDue] = useState(item?.due || "");
  const [paid, setPaid] = useState(item?.paid || false);
  const [msg, setMsg] = useState<Result | null>(null);
  const [pending, start] = useTransition();
  const router = useRouter();
  const run = (p: Promise<Result>) => start(async () => { const r = await p; setMsg(r); if (r.ok) { router.refresh(); onDone(); } });
  const amt = Number(amount.replace(/[$,\s]/g, ""));
  return (
    <div className="space-y-2 bg-[var(--panel-2)] px-4 py-3">
      <div className="grid grid-cols-6 gap-1.5">
        <input className={box + " col-span-3"} placeholder="Label" value={label} onChange={(e) => setLabel(e.target.value)} />
        <input className={box + " col-span-1"} inputMode="decimal" placeholder="$" value={amount} onChange={(e) => setAmount(e.target.value)} />
        <input className={box + " col-span-2"} type="date" value={due} onChange={(e) => setDue(e.target.value)} />
      </div>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={paid} onChange={(e) => setPaid(e.target.checked)} /> Already received</label>
      <div className="flex gap-2">
        <button className="btn btn-primary flex-1" disabled={pending || !amt}
                onClick={() => run(schedule(id, item ? { action: "update", index: item.index, label, amount: amt, due, paid } : { action: "add", label, amount: amt, due, paid }))}>{pending ? "Saving…" : "Save"}</button>
        {item && <button className="btn" disabled={pending} onClick={() => confirm("Remove this payment from the plan?") && run(schedule(id, { action: "delete", index: item.index }))}>Delete</button>}
        <button className="btn" onClick={onDone}>Cancel</button>
      </div>
      {msg && !msg.ok && <p className="text-[13px]" style={{ color: "var(--red)" }}>{msg.msg}</p>}
    </div>
  );
}

export function PlanEditor({ id, items }: { id: string; items: Item[] }) {
  const [edit, setEdit] = useState<number | "new" | null>(null);
  return (
    <>
      {items.map((i) => edit === i.index ? <li key={i.index}><Form id={id} item={i} onDone={() => setEdit(null)} /></li> : (
        <li key={i.index} className="flex items-center justify-between gap-3 px-4 py-3">
          <button className="min-w-0 text-left" onClick={() => setEdit(i.index)}>
            <div className="font-medium">{i.label || "Installment"} <span className="text-[12px] font-normal text-[var(--accent)]">Edit</span></div>
            <div className="text-sm text-[var(--muted)]">{i.dueText}</div>
          </button>
          <div className="flex flex-col items-end gap-1 text-right">
            <div className="font-semibold tabular-nums">{fmt(i.amount)}</div>
            {i.paid ? <span className="chip font-medium" style={{ background: "var(--green-bg)", color: "var(--green)" }}>Paid</span>
              : <>{i.overdue && <span className="chip font-medium" style={{ background: "var(--red-bg)", color: "var(--red)" }}>Overdue</span>}<PayButton id={id} index={i.index} label={i.label || "installment"} /></>}
          </div>
        </li>
      ))}
      <li>{edit === "new" ? <Form id={id} onDone={() => setEdit(null)} /> : <button className="w-full px-4 py-3 text-left text-sm font-medium text-[var(--accent)]" onClick={() => setEdit("new")}>+ Add payment</button>}</li>
    </>
  );
}
