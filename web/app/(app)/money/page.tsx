import Link from "next/link";
import { Suspense } from "react";
import { loadLeads, loadMoney, todayCT } from "@/lib/data";
import { Empty, Pill, Section, day, daysFrom, money, serviceLabel } from "@/components/ui";
import { PageTitle, Skeleton } from "@/components/page-title";
import { Match } from "./match";
import { MoneyTabs } from "./tabs";

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
  const unmatched = pays.filter((p) => !p.leadId);
  const bookings = leads.filter((l) => ["booked", "completed"].includes(l.status) && (l.total || 0) > 0).map((l) => {
    const plan = inst.filter((i) => i.leadId === l.id);
    const paid = l.paid ?? plan.filter((i) => i.paid).reduce((a, b) => a + b.amount, 0);
    const next = plan.filter((i) => !i.paid).sort((a, b) => (a.due || "9").localeCompare(b.due || "9"))[0];
    const d = l.days.find((x) => x.day);
    const first = l.days.map((x) => x.day).filter(Boolean).sort()[0] || null;
    return { l, paid, left: Math.max(0, (l.total || 0) - paid), next, first, what: d?.label || serviceLabel(l.service) };
  });
  // the Match dropdown: bookings that still owe money (they leave the list once paid in full); labels tell same-name
  // clients apart with the event and its date
  const owing = bookings.filter((b) => b.left > 0.005).sort((a, b) => (a.first || "9999").localeCompare(b.first || "9999"))
    .map((b) => ({ id: b.l.id, label: [b.l.client, b.what, b.first ? day(b.first, { month: "short", day: "numeric", year: "numeric" }) : null, `${money(b.left)} left`].filter(Boolean).join(" · ") }));
  const recent = pays.filter((p) => p.leadId).slice(0, 12);
  return (
    <>
      <div className="mt-4 grid grid-cols-2 gap-2.5">
        <div className="card p-4"><div className="text-[12px] text-[var(--muted)]">Received this month</div><div className="text-2xl font-semibold tabular-nums">{money(thisMonth)}</div></div>
        <div className="card p-4"><div className="text-[12px] text-[var(--muted)]">Received in {year}</div><div className="text-2xl font-semibold tabular-nums">{money(thisYear)}</div></div>
        <div className="card p-4"><div className="text-[12px] text-[var(--muted)]">Still to collect</div><div className="text-2xl font-semibold tabular-nums">{money(bookings.reduce((a, b) => a + b.left, 0))}</div></div>
        <div className="card p-4"><div className="text-[12px] text-[var(--muted)]">{year} bookings</div><div className="text-2xl font-semibold tabular-nums">{booked.length}</div></div>
      </div>

      {unmatched.length > 0 && (
        <Section title={`To match (${unmatched.length})`}>
          <p className="mb-2 px-1 text-[13px] text-[var(--muted)]">Zelles we couldn&apos;t tie to a client automatically (often a parent, sibling or in-law paid). Tap Match and pick the booking it&apos;s for.</p>
          <ul className="card divide-y divide-[var(--line)]">
            {unmatched.map((p) => (
              <li key={p.emailId} className="flex flex-wrap items-center justify-between gap-x-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{p.sender || "Unknown sender"}</div>
                  <div className="text-sm text-[var(--muted)]">{day(p.on, { month: "short", day: "numeric", year: "numeric" })}{p.method ? ` · ${p.method}` : ""}</div>
                </div>
                <div className="flex items-center gap-2"><span className="font-semibold tabular-nums" style={{ color: "var(--green)" }}>{money(p.amount)}</span>
                  {p.emailId && <Match emailId={p.emailId} owing={owing} />}</div>
              </li>
            ))}
          </ul>
        </Section>
      )}

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

      <Section title="Bookings">
        {bookings.length ? (
          <ul className="card divide-y divide-[var(--line)]">
            {[...bookings].sort((a, b) => (b.first || "").localeCompare(a.first || "")).map(({ l, paid, left, next, first }) => (
              <li key={l.id}><Link href={`/leads/${l.id}`} className="block px-4 py-3">
                <div className="flex items-baseline justify-between gap-2"><span className="truncate font-medium">{l.client}</span><span className="text-sm text-[var(--muted)]">{first ? day(first, { month: "short", day: "numeric", year: "2-digit" }) : ""}</span></div>
                <div className="mt-1 grid grid-cols-3 text-[13px]">
                  <span><span className="text-[var(--muted)]">Total </span>{money(l.total)}</span>
                  <span><span className="text-[var(--muted)]">Paid </span>{money(paid)}</span>
                  <span className="text-right" style={{ color: left ? (next?.due && daysFrom(today, next.due) < 0 ? "var(--red)" : "var(--ink)") : "var(--green)" }}>{left ? `${money(left)} left` : "Paid in full"}</span>
                </div>
                {next && <div className="text-[12px] text-[var(--muted)]">Next: {money(next.amount)}{next.due ? ` · ${day(next.due)}` : ""}</div>}
              </Link></li>
            ))}
          </ul>
        ) : <Empty>No bookings with a total yet.</Empty>}
      </Section>

      <Section title="Recently received">
        {recent.length ? (
          <ul className="card divide-y divide-[var(--line)]">
            {recent.map((p) => (
              <li key={p.emailId} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0"><div className="truncate font-medium">{name.get(p.leadId!) || p.label || p.sender}</div>
                  <div className="text-sm text-[var(--muted)]">{day(p.on)}{p.sender && name.get(p.leadId!) && !name.get(p.leadId!)!.toLowerCase().includes(p.sender.split(" ")[0].toLowerCase()) ? ` · from ${p.sender}` : ""}</div></div>
                <div className="font-semibold tabular-nums" style={{ color: "var(--green)" }}>{money(p.amount)}</div>
              </li>
            ))}
          </ul>
        ) : <Empty>No matched payments yet.</Empty>}
      </Section>
    </>
  );
}

export default function MoneyPage() {
  return (
    <>
      <PageTitle title="Money" />
      <MoneyTabs active="overview" />
      <Suspense fallback={<Skeleton />}><Money /></Suspense>
    </>
  );
}
