"use client";
import { useState, useTransition } from "react";
import type { Facts } from "@/lib/facts";
import { addAsLead, draftToEman, markDone, notALead, reopen, type Result } from "./actions";

export type CardData = {
  id: string; kind: string; tone: string; who: string; when: string; fromEmail: string | null; leadId: string | null;
  leadName: string | null; subject: string; facts: Facts; count: number; isPerson: boolean;
};

function offerCall(first: string) {
  return `Hi ${first},\n\nThank you so much for reaching out, and congratulations! [Pick one: Great news, that date works for us! / Unfortunately that date doesn't work for us, but I'd still love to help.]\n\nI'd be more than happy to hop on a quick 15-minute call to hear more about what you have in mind and make sure we can cover everything you need. Just let me know a day and time that works best for you.\n\nLooking forward to chatting!\nEman`;
}
function askDetails(first: string) {
  return `Hi ${first},\n\nThank you so much for reaching out! I'd love to help. Could you share a little more about what you're looking for: the type of event or session, the date and location, and roughly how many hours of coverage you have in mind?\n\nOnce I know a bit more, I'll send over the details. I'm also happy to hop on a quick 15-minute call if that's easier.\n\nLooking forward to hearing from you!\nEman`;
}

export function AlertCard({ a }: { a: CardData }) {
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<Result | null>(null);
  const [gone, setGone] = useState(false);
  const [mode, setMode] = useState<"" | "reply" | "lead">("");
  const first = /^[A-Za-z][A-Za-z'-]+$/.test(a.who.split(" ")[0]) ? a.who.split(" ")[0] : "there";
  const [body, setBody] = useState("");
  const [name, setName] = useState(a.who);
  const [handled, setHandled] = useState(false);
  const f = a.facts;
  const blank = `Hi ${first},\n\n\n\nEman`;          // "Other": write your own reply between the greeting and the name
  const squash = (t: string) => t.replace(/\s+/g, " ").trim();
  const run = (p: Promise<Result>, hide = true) => start(async () => { const r = await p; setMsg(r); if (r.ok && hide) setTimeout(() => setGone(true), 900); });
  if (gone) return null;
  if (handled) return (
    <article className="card flex items-center justify-between gap-3 p-4 text-[14px]">
      <span><b>{a.who}</b> moved to Handled.<span className="block text-[12px] text-[var(--muted)]">No email was sent. Also undoable later in Inbox → Handled.</span></span>
      <button className="btn shrink-0" disabled={pending} onClick={() => start(async () => { const r = await reopen(a.id, false); if (r.ok) setHandled(false); else setMsg(r); })}>Undo</button>
    </article>
  );
  const chips = [f.service, ...f.dates.map((d) => "📅 " + d), f.time && "🕓 " + f.time, f.place && "📍 " + f.place, f.hours && "⏱ " + f.hours, f.guests && "👥 " + f.guests, f.video && "🎥 Photo + video"].filter(Boolean) as string[];

  return (
    <article className="card p-4">
      <div className="flex items-start gap-3">
        <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: `var(--${a.tone})` }} aria-hidden />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <h3 className="truncate text-[16px] font-semibold">{a.who}</h3>
            <span className="shrink-0 text-xs text-[var(--muted)]">{a.when}</span>
          </div>
          <div className="text-[13px] text-[var(--muted)]">{a.kind}{a.count > 1 ? ` · ${a.count} messages` : ""}{a.leadName ? ` · ${a.leadName}` : ""}</div>
        </div>
      </div>
      {chips.length > 0 && <div className="mt-3 flex flex-wrap gap-1.5">{chips.map((c) => <span key={c} className="chip">{c}</span>)}</div>}
      {f.excerpt && <p className="mt-3 line-clamp-3 text-[14.5px] leading-snug">{f.excerpt}</p>}
      {f.callTip && <p className="mt-2 text-[13px] font-medium text-[var(--accent)]">They named a date: offer a quick 15-min call with Eman.</p>}

      {mode === "reply" && (
        <div className="mt-3 space-y-2">
          <div className="grid grid-cols-3 gap-2">
            <button className="btn" onClick={() => { setBody(offerCall(first)); }}>📞 Offer a call</button>
            <button className="btn" onClick={() => { setBody(askDetails(first)); }}>✉️ Ask details</button>
            <button className="btn" onClick={() => setBody(blank)}>✍️ Other</button>
          </div>
          {body && <>
            <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={9} autoFocus className="w-full rounded-xl border border-[var(--line)] bg-[var(--bg)] p-3 text-[15px] leading-snug" />
            <p className="text-[12px] text-[var(--muted)]">This goes only to Ibrahim&apos;s inbox for review. Nothing is sent to the client.</p>
            <div className="flex gap-2">
              <button disabled={pending || body.length < 20 || squash(body) === squash(blank)} className="btn btn-primary flex-1"
                      onClick={() => run(draftToEman(a.id, a.subject || "Your message", body), false)}>
                {pending ? "Emailing…" : "📧 Email draft to Ibrahim"}
              </button>
              <button className="btn" disabled={pending} onClick={() => { setBody(""); setMode(""); setMsg(null); }}>Discard</button>
            </div>
          </>}
        </div>
      )}
      {mode === "lead" && (
        <div className="mt-3 space-y-2">
          <label className="block text-sm text-[var(--muted)]">Client name
            <input value={name} onChange={(e) => setName(e.target.value)} className="mt-1 w-full rounded-xl border border-[var(--line)] bg-[var(--bg)] px-3 py-2.5 text-[15px] text-[var(--ink)]" />
          </label>
          <button disabled={pending || !name.trim()} className="btn btn-primary w-full"
                  onClick={() => run(addAsLead(a.id, name.trim(), [f.service, ...f.dates, f.time, f.place, f.hours, f.guests, f.excerpt, a.fromEmail && `(${a.fromEmail})`].filter(Boolean).join(" · "), f.iso[0] || "", a.fromEmail))}>
            {pending ? "Adding…" : `Add lead${f.iso[0] ? " with event " + f.dates[0] : ""}`}
          </button>
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {a.isPerson && a.fromEmail && <button className="btn btn-primary" onClick={() => setMode(mode === "reply" ? "" : "reply")}>Reply</button>}
        {a.isPerson && !a.leadId && <button className="btn" onClick={() => setMode(mode === "lead" ? "" : "lead")}>Add as lead</button>}
        {!(mode === "reply" && body) && <button className="btn" disabled={pending} onClick={() => start(async () => { const r = await markDone(a.id, false); if (r.ok) setHandled(true); else setMsg(r); })}>Mark handled</button>}
        {a.isPerson && !a.leadId && <button className="btn ml-auto border-transparent text-[var(--muted)]" disabled={pending} onClick={() => run(notALead(a.id))}>Not a lead</button>}
      </div>
      {msg && <p role="status" className="mt-2 text-[13px]" style={{ color: msg.ok ? "var(--green)" : "var(--red)" }}>{msg.ok ? "✓ " : ""}{msg.msg}</p>}
    </article>
  );
}
