import Link from "next/link";
import { Suspense } from "react";
import { notFound } from "next/navigation";
import { loadLeads, loadMoney, todayCT } from "@/lib/data";
import { Pill, Section, StatusPill, day, daysFrom, money } from "@/components/ui";
import { serviceLabel } from "@/components/ui";
import { Skeleton } from "@/components/page-title";

const CONTRACT: Record<string, [string, string]> = { signed: ["Signed", "green"], sent: ["Sent", "amber"], not_sent: ["Not sent", "grey"], unknown: ["Unknown", "grey"], "n/a": ["—", "grey"] };
const PAY: Record<string, [string, string]> = { paid: ["Paid", "green"], paid_in_full: ["Paid in full", "green"], partial: ["Partly paid", "amber"], unpaid: ["Unpaid", "red"], due: ["Due", "amber"], unknown: ["Unknown", "grey"], "n/a": ["—", "grey"] };
const CALL: Record<string, [string, string]> = { none: ["Not offered", "grey"], offered: ["Offered", "amber"], booked: ["Booked", "green"], done: ["Done", "green"], declined: ["Declined", "grey"] };

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return <div className="flex items-center justify-between gap-3 px-4 py-3"><span className="text-[var(--muted)]">{k}</span><span className="text-right">{children}</span></div>;
}

async function Detail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const today = await todayCT();
  const [{ leads }, { inst, pays }] = await Promise.all([loadLeads(), loadMoney()]);
  const l = leads.find((x) => x.id === id);
  if (!l) notFound();
  const plan = inst.filter((i) => i.leadId === id);
  const got = pays.filter((p) => p.leadId === id);
  const tag = (m: Record<string, [string, string]>, v: string | null) => { const [t, tone] = m[v || "n/a"] || [v || "—", "grey"]; return <Pill tone={tone}>{t}</Pill>; };
  return (
    <>
      <div className="pt-3"><Link href="/leads" className="text-sm font-medium text-[var(--accent)]">‹ Leads</Link></div>
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

      <Section title="Booking">
        <div className="card divide-y divide-[var(--line)] text-[15px]">
          <Row k="15-min call">{tag(CALL, l.call)}{l.callOn && <span className="ml-2 text-sm">{day(l.callOn)} {l.callTime || ""}</span>}</Row>
          <Row k="Contract">{tag(CONTRACT, l.contract)}</Row>
          <Row k="Retainer">{tag(PAY, l.retainer)}</Row>
          <Row k="Balance">{tag(PAY, l.balance)}</Row>
          <Row k="Total">{money(l.total)}</Row>
        </div>
      </Section>

      {(plan.length > 0 || got.length > 0) && (
        <Section title="Payments">
          <ul className="card divide-y divide-[var(--line)]">
            {plan.map((i, k) => (
              <li key={"i" + k} className="flex items-center justify-between px-4 py-3">
                <div><div className="font-medium">{i.label || "Installment"}</div><div className="text-sm text-[var(--muted)]">{i.paid ? `Paid ${day(i.paidOn)}` : i.due ? `Due ${day(i.due)}` : "No date"}</div></div>
                <div className="text-right"><div className="font-semibold tabular-nums">{money(i.amount)}</div>{!i.paid && i.due && daysFrom(today, i.due) < 0 ? <Pill tone="red">Overdue</Pill> : i.paid ? <Pill tone="green">Paid</Pill> : null}</div>
              </li>
            ))}
            {got.map((p, k) => (
              <li key={"p" + k} className="flex items-center justify-between px-4 py-3">
                <div><div className="font-medium">Received{p.method ? ` · ${p.method}` : ""}</div><div className="text-sm text-[var(--muted)]">{day(p.on)}</div></div>
                <div className="font-semibold tabular-nums" style={{ color: "var(--green)" }}>{money(p.amount)}</div>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {(l.notes || l.email) && (
        <Section title="Notes">
          <div className="card space-y-2 p-4 text-[15px]">
            {l.email && <a href={`mailto:${l.email}`} className="block text-[var(--accent)]">{l.email}</a>}
            {l.notes && <p className="whitespace-pre-line leading-snug">{l.notes}</p>}
          </div>
        </Section>
      )}
      <p className="mt-6 text-center text-xs text-[var(--muted)]">Editing a lead from the phone comes next. For now: <a className="underline" href="https://ev-dashboard-tan.vercel.app">full dashboard</a>.</p>
    </>
  );
}

export default function LeadPage(props: PageProps<"/leads/[id]">) {
  return <Suspense fallback={<Skeleton />}><Detail params={props.params as Promise<{ id: string }>} /></Suspense>;
}
