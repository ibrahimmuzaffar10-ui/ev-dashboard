"use client";
import { useState, useTransition } from "react";
import { markReceived } from "../actions";

export function PayButton({ id, index, label }: { id: string; index: number; label: string }) {
  const [state, setState] = useState<"" | "ask" | "done" | string>("");
  const [pending, start] = useTransition();
  if (state === "done") return <span className="text-[13px] font-medium" style={{ color: "var(--green)" }}>✓ Received</span>;
  if (state === "ask") return (
    <span className="flex gap-1.5">
      <button className="btn btn-primary !min-h-8 !px-3 !py-1 text-[13px]" disabled={pending}
              onClick={() => start(async () => { const r = await markReceived(id, index); setState(r.ok ? "done" : r.msg); })}>{pending ? "…" : "Confirm"}</button>
      <button className="btn !min-h-8 !px-3 !py-1 text-[13px]" onClick={() => setState("")}>Cancel</button>
    </span>
  );
  return (
    <span className="flex flex-col items-end gap-1">
      <button className="btn !min-h-8 !px-3 !py-1 text-[13px]" onClick={() => setState("ask")} aria-label={`Mark ${label} received`}>Mark received</button>
      {state && <span className="text-[12px]" style={{ color: "var(--red)" }}>{state}</span>}
    </span>
  );
}
