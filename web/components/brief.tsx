"use client";
import { useState, useTransition } from "react";
import { ackBrief } from "@/app/(app)/brief-actions";

// The 7 AM / 10 PM brief (written on the Mac by brief.py). Plain-text markdown rendered as React, never as raw HTML.
function Inline({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|_[^_]+_)/g);
  return <>{parts.map((p, i) => p.startsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> : p.startsWith("_") && p.endsWith("_") ? <em key={i}>{p.slice(1, -1)}</em> : p)}</>;
}

export function Brief({ brief, acked }: { brief: { id: string; slot: string; text: string; at: string }; acked: boolean }) {
  const [open, setOpen] = useState(!acked);
  const [read, setRead] = useState(acked);
  const [pending, start] = useTransition();
  const lines = brief.text.split("\n").filter((l) => !l.startsWith("## "));
  return (
    <section className="card mt-4 overflow-hidden">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between px-4 py-3 text-left">
        <span className="font-semibold">{brief.slot === "Morning" ? "☀️ Morning brief" : "🌙 Night brief"}{!read && <span className="ml-2 rounded-full px-2 py-0.5 text-[11px]" style={{ background: "var(--accent)", color: "var(--accent-ink)" }}>new</span>}</span>
        <span className="text-[var(--muted)]">{open ? "–" : "+"}</span>
      </button>
      {open && (
        <div className="space-y-1 border-t border-[var(--line)] px-4 py-3 text-[14.5px] leading-snug">
          {lines.map((l, i) => !l.trim() ? <div key={i} className="h-1.5" /> : l.startsWith("- ")
            ? <div key={i} className="pl-3"><Inline text={l.slice(2)} /></div>
            : <div key={i} className={l.startsWith("**") ? "pt-1 font-semibold" : "text-[var(--muted)]"}><Inline text={l} /></div>)}
          {!read && <button className="btn btn-primary mt-3 w-full" disabled={pending}
                            onClick={() => start(async () => { await ackBrief(brief.id); setRead(true); setOpen(false); })}>Got it</button>}
        </div>
      )}
    </section>
  );
}
