import Link from "next/link";
import { Suspense } from "react";
import { notFound } from "next/navigation";
import { loadDocs, loadLeads, loadMoney, todayCT } from "@/lib/data";
import { Section, StatusPill, day, daysFrom, money } from "@/components/ui";
import { serviceLabel } from "@/components/ui";
import { Skeleton } from "@/components/page-title";
import { Editor } from "./editor";
import { PlanEditor } from "./plan";



async function Detail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const today = await todayCT();
  const [{ leads }, { inst, pays }, docs] = await Promise.all([loadLeads(), loadMoney(), loadDocs(id)]);
  const l = leads.find((x) => x.id === id);
  if (!l) notFound();
  const plan = inst.filter((i) => i.leadId === id);
  const got = pays.filter((p) => p.leadId === id);
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

      <Section title="Details"><Editor lead={l} /></Section>

      {(l.status === "booked" || l.status === "completed" || plan.length > 0 || got.length > 0) && (
        <Section title="Payments">
          <ul className="card divide-y divide-[var(--line)]">
            <PlanEditor id={l.id} items={plan.map((i) => ({ ...i, overdue: !i.paid && !!i.due && daysFrom(today, i.due) < 0, dueText: i.paid ? `Paid ${day(i.paidOn)}` : i.due ? `Due ${day(i.due)}` : "No date" }))} />
            {got.map((p, k) => (
              <li key={"p" + k} className="flex items-center justify-between px-4 py-3">
                <div><div className="font-medium">Received{p.method ? ` · ${p.method}` : ""}</div><div className="text-sm text-[var(--muted)]">{day(p.on)}</div></div>
                <div className="font-semibold tabular-nums" style={{ color: "var(--green)" }}>{money(p.amount)}</div>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {docs.length > 0 && (
        <Section title="Documents">
          <ul className="card divide-y divide-[var(--line)]">
            {docs.map((d) => (
              <li key={d.id}><a href={`/files/${d.id}`} target="_blank" rel="noopener" className="flex items-center gap-3 px-4 py-3">
                <span className="text-lg" aria-hidden>{d.name.toLowerCase().endsWith(".pdf") ? "📄" : "📝"}</span>
                <span className="min-w-0 flex-1"><span className="block truncate text-[15px]">{d.kind === "signed" ? "Signed contract" : d.kind === "draft" ? "Contract draft" : d.kind === "questionnaire" ? "Questionnaire" : d.kind}</span>
                  <span className="block truncate text-[12px] text-[var(--muted)]">{d.name.toLowerCase().endsWith(".pdf") ? "PDF · opens here" : "Word · downloads"}</span></span>
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
    </>
  );
}

export default function LeadPage(props: PageProps<"/leads/[id]">) {
  return <Suspense fallback={<Skeleton />}><Detail params={props.params as Promise<{ id: string }>} /></Suspense>;
}
