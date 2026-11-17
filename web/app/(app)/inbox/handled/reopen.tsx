"use client";
import { useState, useTransition } from "react";
import { reopen } from "../actions";

export function Reopen({ id }: { id: string }) {
  const [done, setDone] = useState("");
  const [pending, start] = useTransition();
  if (done) return <span className="text-[13px]" style={{ color: "var(--green)" }}>{done}</span>;
  return <button className="btn !min-h-8 !px-3 !py-1 text-[13px]" disabled={pending} onClick={() => start(async () => { const r = await reopen(id); setDone(r.ok ? "✓ Back in Inbox" : r.msg); })}>Reopen</button>;
}
