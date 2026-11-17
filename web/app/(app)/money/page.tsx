import Link from "next/link";
import { Suspense } from "react";
import { loadLeads, loadMoney, todayCT } from "@/lib/data";
import { Empty, Pill, Section, day, daysFrom, money } from "@/components/ui";
import { PageTitle, Skeleton } from "@/components/page-title";

async function Money() {
  const today = await todayCT();
  const [{ leads }, { inst, pays, error }] = await Promise.all([loadLeads(), loadMoney()]);
  if (error) return <Empty>Couldn&apos;t load: {error}</Empty>;
  const name = new Map(leads.map((l) => [l.id, l.client]));
  const month = today.slice(0, 7), year = today.slice(0, 4);
  const sum = (xs: { amount: number }[]) => xs.reduce((a, b) => a + b.amount, 0);
  const thisMonth = sum(pays.filter((p) => p.on?.startsWith(month)));
  const thisYear = sum(pays.filter((p) => p.on?.startsWith(year)));
  const open = inst.filter((i) => !i.paid);
  const overdue = open.filter((i) => i.due && daysFrom(today, i.due) < 0);
  const next30 = open.filter((i) => i.due && daysFrom(today, i.due) >= 0 && daysFrom(today, i.due) <= 30);
  const booked = leads.filter((l) => ["booked", "completed"].includes(l.status) && l.days.some((d) => d.day?.startsWith(year)));
  return (
    <>
      <div className="mt-4 grid grid-cols-2 gap-2.5">
        <div className="card p-4"><div className="text-[12px] text-[var(--muted)]">Received this month</div><div className="text-2xl font-semibold tabular-nums">{money(thisMonth)}</div></div>
        <div className="card p-4"><div className="text-[12px] text-[var(--muted)]">Received in {year}</div><div className="text-2xl font-semibold tabular-nums">{money(thisYear)}</div></div>
        <div className="card p-4"><div className="text-[12px] text-[var(--muted)]">Still to collect</div><div className="text-2xl font-semibold tabular-nums">{money(sum(open))}</div></div>
        <div className="card p-4"><div className="text-[12px] text-[var(--muted)]">{year} bookings</div><div className="text-2xl font-semibold tabular-nums">{booked.length}</div></div>
      </div>
      {[["Overdue", overdue, "red"], ["Due in the next 30 days", next30, "amber"]].map(([t, list, tone]) => (list as typeof open).length > 0 && (
        <Section key={t as string} title={t as string}>
          <ul className="card divide-y divide-[var(--line)]">
            {(list as typeof open).map((i, k) => (
              <li key={k}><Link href={`/leads/${i.leadId}`} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0"><div className="truncate font-medium">{name.get(i.leadId) || i.leadId}</div><div className="text-sm text-[var(--muted)]">{i.label || "Installment"} · {day(i.due)}</div></div>
                <div className="text-right"><div className="font-semibold tabular-nums">{money(i.amount)}</div><Pill tone={tone as string}>{tone === "red" ? `${-daysFrom(today, i.due!)} d late` : `in ${daysFrom(today, i.due!)} d`}</Pill></div>
              </Link></li>
            ))}
          </ul>
        </Section>
      ))}
      <Section title="Recently received">
        {pays.length ? (
          <ul className="card divide-y divide-[var(--line)]">
            {pays.slice(0, 12).map((p, k) => (
              <li key={k} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0"><div className="truncate font-medium">{(p.leadId && name.get(p.leadId)) || p.label || p.sender || "Unmatched payment"}</div><div className="text-sm text-[var(--muted)]">{day(p.on)}{p.method ? ` · ${p.method}` : ""}{!p.leadId ? " · not matched to a client" : ""}</div></div>
                <div className="font-semibold tabular-nums" style={{ color: "var(--green)" }}>{money(p.amount)}</div>
              </li>
            ))}
          </ul>
        ) : <Empty>No payments yet.</Empty>}
      </Section>
    </>
  );
}

export default function MoneyPage() {
  return (
    <>
      <PageTitle title="Money" />
      <Suspense fallback={<Skeleton />}><Money /></Suspense>
    </>
  );
}
