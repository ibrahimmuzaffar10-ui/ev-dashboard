import Link from "next/link";
import { Suspense } from "react";
import { loadLeads, todayCT, type Lead } from "@/lib/data";
import { Empty, StatusPill, day } from "@/components/ui";
import { serviceLabel } from "@/components/ui";
import { PageTitle, Skeleton } from "@/components/page-title";

const FILTERS: [string, string, (l: Lead, today: string) => boolean][] = [
  ["reply", "Needs reply", (l) => l.status === "unanswered"],
  ["open", "Waiting", (l) => l.status === "open"],
  ["booked", "Booked", (l) => l.status === "booked"],
  ["calls", "Calls", (l) => ["offered", "booked"].includes(l.call)],
  ["past", "Completed", (l) => l.status === "completed"],
  ["lost", "Lost", (l) => ["lost", "ghosted"].includes(l.status)],
  ["all", "All", () => true],
];

const firstDay = (l: Lead) => l.days.find((d) => d.day)?.day || null;

async function List({ searchParams }: { searchParams: Promise<{ f?: string; q?: string }> }) {
  const sp = await searchParams;
  const f = FILTERS.find((x) => x[0] === sp.f) || FILTERS[0];
  const q = (sp.q || "").trim().toLowerCase();
  const today = await todayCT();
  const { leads, error } = await loadLeads();
  if (error) return <Empty>Couldn&apos;t load: {error}</Empty>;
  const counts = Object.fromEntries(FILTERS.map(([k, , fn]) => [k, leads.filter((l) => fn(l, today)).length]));
  let rows = leads.filter((l) => f[2](l, today) && (!q || `${l.client} ${l.email || ""} ${l.notes || ""}`.toLowerCase().includes(q)));
  rows = rows.sort((a, b) => f[0] === "reply" || f[0] === "open" ? (b.inquiry || "").localeCompare(a.inquiry || "")  // leak-check: allow: the app word "inquiry", not client data
    : f[0] === "booked" ? (firstDay(a) || "9999").localeCompare(firstDay(b) || "9999") : (b.inquiry || "").localeCompare(a.inquiry || ""));  // leak-check: allow: the app word "inquiry", not client data
  return (
    <>
      <div className="-mx-4 mt-3 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none]">
        {FILTERS.map(([k, label]) => (
          <Link key={k} href={`/leads?f=${k}${q ? `&q=${encodeURIComponent(q)}` : ""}`} className="chip shrink-0 px-3.5 py-1.5 text-[13.5px] font-medium"
                style={k === f[0] ? { background: "var(--ink)", color: "var(--bg)" } : undefined}>
            {label} <span className="opacity-60 tabular-nums">{counts[k]}</span>
          </Link>
        ))}
      </div>
      <form className="mt-3"><input type="hidden" name="f" value={f[0]} />
        <input name="q" defaultValue={sp.q || ""} placeholder="Search name, email, notes" className="w-full rounded-xl border border-[var(--line)] bg-[var(--panel)] px-3.5 py-2.5 text-[15px]" />
      </form>
      {rows.length ? (
        <ul className="card mt-3 divide-y divide-[var(--line)]">
          {rows.map((l) => {
            const d = firstDay(l);
            return (
              <li key={l.id}>
                <Link href={`/leads/${l.id}`} className="flex items-center gap-3 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{l.client}</div>
                    <div className="truncate text-[13px] text-[var(--muted)]">
                      {[serviceLabel(l.service), d ? "📅 " + day(d, { month: "short", day: "numeric", year: "numeric" }) : l.eventText || null, l.call === "booked" && l.callOn ? "📞 " + day(l.callOn) : l.call === "offered" ? "📞 offered" : null].filter(Boolean).join(" · ") || `Inquired ${day(l.inquiry, { month: "short", day: "numeric" })}`}{/* leak-check: allow: the app word "inquiry", not client data */}
                    </div>
                  </div>
                  <StatusPill status={l.status} />
                </Link>
              </li>
            );
          })}
        </ul>
      ) : <div className="mt-3"><Empty>No leads here.</Empty></div>}
    </>
  );
}

export default function Leads(props: PageProps<"/leads">) {
  return (
    <>
      <PageTitle title="Leads" />
      <Suspense fallback={<Skeleton rows={6} />}><List searchParams={props.searchParams as Promise<{ f?: string; q?: string }>} /></Suspense>
    </>
  );
}
