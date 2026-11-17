import Link from "next/link";
import { Suspense } from "react";
import { loadLeads, todayCT } from "@/lib/data";
import { Empty, Pill, day, daysFrom } from "@/components/ui";
import { PageTitle, Skeleton } from "@/components/page-title";

async function Cal() {
  const today = await todayCT();
  const { leads, error } = await loadLeads();
  if (error) return <Empty>Couldn&apos;t load: {error}</Empty>;
  const items = leads.filter((l) => ["booked", "open", "unanswered"].includes(l.status))
    .flatMap((l) => l.days.filter((d) => d.day && d.day >= today).map((d) => ({ l, d, booked: l.status === "booked" })))
    .sort((a, b) => a.d.day!.localeCompare(b.d.day!));
  if (!items.length) return <Empty>Nothing on the calendar yet.</Empty>;
  const months = new Map<string, typeof items>();
  for (const it of items) { const k = it.d.day!.slice(0, 7); months.set(k, [...(months.get(k) || []), it]); }
  return (
    <div className="mt-2">
      {[...months.entries()].map(([m, list]) => (
        <section key={m} className="mt-5">
          <h2 className="px-1 pb-2 font-serif text-lg font-semibold">{day(m + "-01", { month: "long", year: "numeric" })}</h2>
          <ul className="space-y-2">
            {list.map(({ l, d, booked }, i) => (
              <li key={i}>
                <Link href={`/leads/${l.id}`} className="card flex items-center gap-3 p-3" style={booked ? undefined : { borderStyle: "dashed", boxShadow: "none" }}>
                  <div className="w-11 text-center">
                    <div className="text-[11px] font-semibold uppercase text-[var(--muted)]">{day(d.day, { weekday: "short" })}</div>
                    <div className="text-xl font-semibold leading-none tabular-nums">{Number(d.day!.slice(8, 10))}</div>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{l.client}</div>
                    <div className="truncate text-[13px] text-[var(--muted)]">{[d.label, d.start && d.end ? `${d.start}–${d.end}` : d.start, d.venue || l.venue].filter(Boolean).join(" · ") || "—"}</div>
                  </div>
                  {booked ? <span className="text-xs text-[var(--muted)]">{daysFrom(today, d.day!) === 0 ? "today" : `${daysFrom(today, d.day!)} d`}</span> : <Pill tone="amber">Hold</Pill>}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

export default function Calendar() {
  return (
    <>
      <PageTitle title="Calendar" sub="Booked shoots · dashed = date held for an open inquiry" />{/* leak-check: allow: the app word "inquiry", not client data */}
      <Suspense fallback={<Skeleton rows={6} />}><Cal /></Suspense>
    </>
  );
}
