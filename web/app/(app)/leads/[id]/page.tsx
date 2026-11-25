import Link from "next/link";
import { Suspense } from "react";
import { notFound } from "next/navigation";
import { loadDocs, loadLeads, loadMoney, todayCT } from "@/lib/data";
import { Section, StatusPill, day, daysFrom, money } from "@/components/ui";
import { serviceLabel } from "@/components/ui";
import { Skeleton } from "@/components/page-title";
import { ledger } from "@/lib/money";
import { Editor } from "./editor";
import { OPTS } from "@/lib/lead-options";
import { CloseLead } from "./close";
import { staleWhy } from "@/lib/stale";
import { PlanEditor } from "./plan";

async function Detail({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ from?: string }> }) {
  const { id } = await params;
  const fromInbox = (await searchParams)?.from === "inbox";
  const today = await todayCT();
  const [{ leads }, { inst, pays }, docs] = await Promise.all([loadLeads(), loadMoney(), loadDocs(id)]);
  const l = leads.find((x) => x.id === id);
  if (!l) notFound();
  const plan = inst.filter((i) => i.leadId === id);
  const got = pays.filter((p) => p.leadId === id);
  const g = ledger(l, pays);
  const stale = staleWhy(l, today);
  return (
    <>
      <div className="pt-3"><Link href={fromInbox ? "/inbox" : "/leads"} className="text-sm font-medium text-[var(--accent)]">{fromInbox ? "‹ Inbox" : "‹ Leads"}</Link></div>
      <header className="mt-2">
        <h1 className="font-serif text-[26px] font-semibold leading-tight">{l.client}</h1>
        <div className="mt-1.5 flex flex-wrap items-center gap-2 text-sm text-[var(--muted)]">
          <StatusPill status={l.status} />
          {serviceLabel(l.service) && <span className="chip">{serviceLabel(l.service)}</span>}
          {l.channel && <span>via {l.channel}</span>}
        </div>
      </header>

      {l.next && <div className="card mt-4 border-l-4 p-4 text-[15px]" style={{ borderLeftColor: "var(--accent)" }}><div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Next step</div>{l.next}</div>}

      <Section title="Event">
        <div className="card divide-y divide-[var(--line)]">
          {l.days.length ? l.days.map((d, i) => (
            <div key={i} className="px-4 py-3">
              <div className="font-medium">{d.day ? day(d.day, { weekday: "long", month: "long", day: "numeric", year: "numeric" }) : "Date to confirm"}{d.day && daysFrom(today, d.day) >= 0 ? <span className="ml-2 text-sm font-normal text-[var(--muted)]">in {daysFrom(today, d.day)} days</span> : null}</div>
              <div className="text-sm text-[var(--muted)]">{[d.label, d.start && d.end ? `${d.start}–${d.end}` : d.start, d.venue || l.venue].filter(Boolean).join(" · ")}</div>
            </div>
          )) : <div className="px-4 py-3 text-[var(--muted)]">{l.eventText || "No date yet"}{l.venue ? ` · ${l.venue}` : ""}</div>}
        </div>
      </Section>

      {stale && <div className="card mt-4 border-l-4 p-4 text-[14px]" style={{ borderLeftColor: "var(--amber)" }}><b>Looks stale:</b> {stale.text}. If it&apos;s not going anywhere, close it at the bottom of this page.</div>}

      <Section title="Details"><Editor key={`${l.status}-${(l.notes || "").length}`} lead={l} /></Section>

      {(l.status === "booked" || l.status === "completed" || plan.length > 0 || got.length > 0) && (
        <>
          <Section title="Payments">
            <div className="card mb-2.5 grid grid-cols-3 gap-2 p-4 text-center">
              <div><div className="text-[12px] text-[var(--muted)]">Total</div><div className="font-semibold tabular-nums">{g.total === null ? "Not set" : money(g.total)}</div></div>
              <div><div className="text-[12px] text-[var(--muted)]">Received</div><div className="font-semibold tabular-nums">{money(g.paid)}</div></div>
              <div><div className="text-[12px] text-[var(--muted)]">{g.tip > 0 ? "Tip" : g.complete ? "Status" : "Left"}</div>
                <div className="font-semibold tabular-nums" style={{ color: g.complete ? "var(--green)" : "var(--ink)" }}>{g.tip > 0 ? `+${money(g.tip)}` : g.complete ? "Paid in full" : g.total === null ? "—" : money(g.left)}</div></div>
              {g.total !== null && <div className="col-span-3 mt-1 h-1.5 overflow-hidden rounded-full bg-[var(--panel-2)]" aria-hidden><div className="h-full rounded-full" style={{ width: `${Math.min(100, (g.paid / g.total) * 100)}%`, background: g.complete ? "var(--chart-1)" : "var(--chart-3)" }} /></div>}
            </div>
            <div className="mb-1 px-1 text-[12px] font-semibold uppercase tracking-wide text-[var(--muted)]">Plan</div>
            <ul className="card divide-y divide-[var(--line)]">
              <PlanEditor id={l.id} items={plan.map((i) => ({ ...i, overdue: !i.paid && !!i.due && daysFrom(today, i.due) < 0, dueText: i.paid ? `Paid ${i.paidOn ? day(i.paidOn) : ""}`.trim() : i.due ? `Due ${day(i.due)}` : "No date" }))} />
            </ul>
          </Section>
          <Section title="Payment history">
            {g.entries.length || g.untracked ? (
              <ol className="card divide-y divide-[var(--line)]">
                {g.untracked > 0 && (
                  <li className="flex items-center justify-between gap-3 px-4 py-3">
                    <div className="min-w-0"><div className="font-medium">Earlier payments</div><div className="text-[13px] text-[var(--muted)]">Marked paid, no Zelle on file (cash, other app, or before tracking)</div></div>
                    <div className="text-right"><div className="font-semibold tabular-nums">{money(g.untracked)}</div></div>
                  </li>
                )}
                {g.entries.map((p, k) => (
                  <li key={k} className="flex items-center justify-between gap-3 px-4 py-3">
                    <div className="min-w-0">
                      <div className="font-medium">{day(p.on, { month: "short", day: "numeric", year: "numeric" })}{p.method ? <span className="font-normal text-[var(--muted)]"> · {p.method}</span> : null}</div>
                      <div className="truncate text-[13px] text-[var(--muted)]">{p.sender ? `from ${p.sender}` : "Payment"}{g.total !== null ? ` · ${money(p.running)} of ${money(g.total)}` : ` · ${money(p.running)} so far`}</div>
                      {p.fullHere && <span className="chip mt-1 font-medium" style={{ background: "var(--green-bg)", color: "var(--green)" }}>✓ Paid in full here</span>}
                    </div>
                    <div className="font-semibold tabular-nums" style={{ color: "var(--green)" }}>{money(p.amount)}</div>
                  </li>
                ))}
                {g.tip > 0 && <li className="flex items-center justify-between px-4 py-3 text-[14px]"><span className="text-[var(--muted)]">Extra above the total (tip)</span><span className="font-semibold tabular-nums" style={{ color: "var(--green)" }}>+{money(g.tip)}</span></li>}
              </ol>
            ) : <div className="card px-4 py-3 text-[14px] text-[var(--muted)]">No payments received yet.</div>}
          </Section>
        </>
      )}

      {docs.length > 0 && (
        <Section title="Documents">
          <ul className="card divide-y divide-[var(--line)]">
            {docs.map((d) => (
              <li key={d.id}><a href={`/files/${d.id}`} target="_blank" rel="noopener" className="flex items-center gap-3 px-4 py-3">
                <span className="text-lg" aria-hidden>{d.label.startsWith("✅") ? "✅" : d.pdf ? "📄" : "📝"}</span>
                <span className="min-w-0 flex-1"><span className={"block truncate text-[15px]" + (d.current ? " font-semibold" : "")}>{d.label.replace(/^✅ /, "")}</span>
                  <span className="block truncate text-[12px] text-[var(--muted)]">{d.note}</span></span>
                <span className="text-[var(--muted)]">›</span>
              </a></li>
            ))}
          </ul>
        </Section>
      )}
      {l.email && <p className="mt-4 text-center text-[15px]"><a href={`mailto:${l.email}`} className="text-[var(--accent)]">{l.email}</a></p>}
      {["open", "booked", "unanswered"].includes(l.status) && (
        <Link href={`/leads/${l.id}/contract`} className="btn mt-4 w-full">📄 {l.contract && !["n/a", "unknown"].includes(l.contract) ? "Re-create contract" : "Create contract"}</Link>
      )}
      {["unanswered", "open", "ghosted", "lost"].includes(l.status) && (
        <CloseLead id={l.id} status={l.status} notes={l.notes || ""} suggest={stale?.reason || ""} stamp={day(today, { month: "short", day: "numeric", year: "numeric" })}
                   why={OPTS.lost_reason.find(([k]) => k === l.lostReason)?.[1] || null} />
      )}
    </>
  );
}

export default function LeadPage(props: PageProps<"/leads/[id]">) {
  return <Suspense fallback={<Skeleton />}><Detail params={props.params as Promise<{ id: string }>} searchParams={props.searchParams as Promise<{ from?: string }>} /></Suspense>;
}
