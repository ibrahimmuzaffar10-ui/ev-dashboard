import { Suspense } from "react";
import { loadLeads, loadMoney, todayCT } from "@/lib/data";
import { Empty, Section, money } from "@/components/ui";
import { PageTitle, Skeleton } from "@/components/page-title";
import { BarChart, type Bar } from "@/components/charts";
import { monthSplit } from "@/lib/money";
import { MoneyTabs } from "../tabs";

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];  // for the stat tiles
function months(from: string, count: number) {          // "YYYY-MM" keys starting at `from`
  const [y, m] = from.split("-").map(Number);
  return Array.from({ length: count }, (_, i) => { const d = new Date(Date.UTC(y, m - 1 + i, 1)); return d.toISOString().slice(0, 7); });
}
const shift = (ym: string, n: number) => { const [y, m] = ym.split("-").map(Number); return new Date(Date.UTC(y, m - 1 + n, 1)).toISOString().slice(0, 7); };

function Stat({ k, v, s }: { k: string; v: string; s?: string }) {
  return <div className="card p-4"><div className="text-[12px] text-[var(--muted)]">{k}</div><div className="text-2xl font-semibold tabular-nums">{v}</div>{s && <div className="text-[12px] text-[var(--muted)]">{s}</div>}</div>;
}

async function Progress() {
  const today = await todayCT();
  const [{ leads }, { inst, pays: allPays, error }] = await Promise.all([loadLeads(), loadMoney()]);
  const pays = allPays.filter((p) => !p.personal);          // business income only
  if (error) return <Empty>Couldn&apos;t load: {error}</Empty>;
  const ym = today.slice(0, 7), year = today.slice(0, 4);
  const sumBy = <T,>(xs: T[], key: (x: T) => string | null | undefined, val: (x: T) => number) => {
    const m = new Map<string, number>(); for (const x of xs) { const k = key(x); if (k) m.set(k, (m.get(k) || 0) + val(x)); } return m;
  };
  const received = sumBy(pays, (p) => p.on?.slice(0, 7), (p) => p.amount);
  const split = monthSplit(leads, pays);
  const scheduled = sumBy(inst.filter((i) => !i.paid && i.due), (i) => (i.due! < today ? ym : i.due!.slice(0, 7)), (i) => i.amount);  // overdue counts as this month
  // money: from the first payment on file (at least 12 months back) through 6 months ahead; swipe for older months
  const firstPay = [...received.keys()].sort()[0] || ym;
  const start = firstPay < shift(ym, -11) ? firstPay : shift(ym, -11);
  const span = (from: string, to: string) => { let n = 0; for (let k = from; k <= to; k = shift(k, 1)) n++; return n; };
  const mKeys = months(start, span(start, shift(ym, 6)));
  const moneyBars: Bar[] = mKeys.map((k) => { const m = split.get(k) || { full: 0, partial: 0 }; return { ym: k, v: [Math.round(m.full), Math.round(m.partial), Math.round(k >= ym ? scheduled.get(k) || 0 : 0)] }; });
  // inquiries vs bookings by the month they inquired
  const firstInq = leads.map((l) => l.inquiry?.slice(0, 7)).filter(Boolean).sort()[0] as string | undefined;  // leak-check: allow: the app field name "inquiry", not client data
  const iStart = firstInq && firstInq < shift(ym, -11) ? firstInq : shift(ym, -11);
  const iKeys = months(iStart, span(iStart, ym));
  const inq = sumBy(leads, (l) => l.inquiry?.slice(0, 7), () => 1);  // leak-check: allow: the app field name "inquiry", not client data
  const won = sumBy(leads.filter((l) => ["booked", "completed"].includes(l.status)), (l) => l.inquiry?.slice(0, 7), () => 1);  // leak-check: allow: the app field name "inquiry", not client data
  const funnelBars: Bar[] = iKeys.map((k) => ({ ym: k, v: [inq.get(k) || 0, won.get(k) || 0] }));
  // headline numbers
  const ytd = [...received].filter(([k]) => k.startsWith(year)).reduce((a, [, v]) => a + v, 0);
  const lastYearSame = [...received].filter(([k]) => k.startsWith(String(Number(year) - 1)) && k.slice(5) <= ym.slice(5)).reduce((a, [, v]) => a + v, 0);
  const best = [...received].sort((a, b) => b[1] - a[1])[0];
  const monthsSoFar = Number(ym.slice(5));
  const ahead = [...scheduled].filter(([k]) => k >= ym).reduce((a, [, v]) => a + v, 0);
  const last12 = funnelBars.slice(-12), inq12 = last12.reduce((a, b) => a + b.v[0], 0), won12 = last12.reduce((a, b) => a + b.v[1], 0);
  return (
    <>
      <div className="mt-4 grid grid-cols-2 gap-2.5">
        <Stat k={`Received in ${year}`} v={money(ytd)} s={lastYearSame ? `${ytd >= lastYearSame ? "▲" : "▼"} ${money(Math.abs(ytd - lastYearSame))} vs same time last year` : `about ${money(ytd / monthsSoFar)} a month`} />
        <Stat k="Best month" v={best ? money(best[1]) : "—"} s={best ? `${MON[Number(best[0].slice(5)) - 1]} ${best[0].slice(0, 4)}` : undefined} />
        <Stat k="Scheduled to come in" v={money(ahead)} s="unpaid installments from this month on" />
        <Stat k="Booking rate (12 months)" v={inq12 ? `${Math.round((won12 / inq12) * 100)}%` : "—"} s={`${won12} booked of ${inq12} inquiries`} />{/* leak-check: allow: the app word "inquiry", not client data */}
      </div>
      <Section title="Money by month">
        <BarChart title="Money in" layout="stack" money focus={mKeys.indexOf(ym)} bars={moneyBars}
                  series={[{ name: "Paid in full that month", color: "var(--chart-1)" }, { name: "Partial payments", color: "var(--chart-3)" }, { name: "Scheduled", color: "var(--chart-1)", dashed: true }]}
                  note="Each payment counts in the month it arrived, not the event month. Green: the booking was paid off that month (all at once, or its last payment). Gold: a deposit or installment toward a booking still being paid off. Dashed: installments still due. Tap a color for its amount, or the month for its total; tap a client in Money to see every payment." />
      </Section>
      <Section title="Inquiries and bookings">{/* leak-check: allow: the app word "inquiry", not client data */}
        <BarChart title="By the month they inquired" layout="pair" money={false} focus={iKeys.length - 1} bars={funnelBars}
                  series={[{ name: "Inquiries", color: "var(--chart-2)" }, { name: "Booked", color: "var(--chart-1)" }]} />{/* leak-check: allow: the app word "inquiry", not client data */}
      </Section>
    </>
  );
}

export default function ProgressPage() {
  return (
    <>
      <PageTitle title="Money" />
      <MoneyTabs active="progress" />
      <Suspense fallback={<Skeleton />}><Progress /></Suspense>
    </>
  );
}
