import { Suspense } from "react";
import { loadLeads, loadMoney, todayCT } from "@/lib/data";
import { Empty, Section, money } from "@/components/ui";
import { PageTitle, Skeleton } from "@/components/page-title";
import { BarChart, type Bar } from "@/components/charts";
import { MoneyTabs } from "../tabs";

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
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
  const scheduled = sumBy(inst.filter((i) => !i.paid && i.due), (i) => (i.due! < today ? ym : i.due!.slice(0, 7)), (i) => i.amount);  // overdue counts as this month
  // money: 9 months back · this month · 6 months ahead
  const mKeys = months(shift(ym, -9), 16);
  const moneyBars: Bar[] = mKeys.map((k) => ({ label: MON[Number(k.slice(5)) - 1], sub: k.slice(0, 4), a: Math.round(k <= ym ? received.get(k) || 0 : 0), b: Math.round(k >= ym ? scheduled.get(k) || 0 : 0) }));
  // inquiries vs bookings by the month they inquired (last 12 months)
  const iKeys = months(shift(ym, -11), 12);
  const inq = sumBy(leads, (l) => l.inquiry?.slice(0, 7), () => 1);  // leak-check: allow: the app field name "inquiry", not client data
  const won = sumBy(leads.filter((l) => ["booked", "completed"].includes(l.status)), (l) => l.inquiry?.slice(0, 7), () => 1);  // leak-check: allow: the app field name "inquiry", not client data
  const funnelBars: Bar[] = iKeys.map((k) => ({ label: MON[Number(k.slice(5)) - 1], sub: k.slice(0, 4), a: inq.get(k) || 0, b: won.get(k) || 0 }));
  // headline numbers
  const ytd = [...received].filter(([k]) => k.startsWith(year)).reduce((a, [, v]) => a + v, 0);
  const lastYearSame = [...received].filter(([k]) => k.startsWith(String(Number(year) - 1)) && k.slice(5) <= ym.slice(5)).reduce((a, [, v]) => a + v, 0);
  const best = [...received].sort((a, b) => b[1] - a[1])[0];
  const monthsSoFar = Number(ym.slice(5));
  const ahead = [...scheduled].filter(([k]) => k >= ym).reduce((a, [, v]) => a + v, 0);
  const inq12 = funnelBars.reduce((a, b) => a + b.a, 0), won12 = funnelBars.reduce((a, b) => a + (b.b || 0), 0);
  return (
    <>
      <div className="mt-4 grid grid-cols-2 gap-2.5">
        <Stat k={`Received in ${year}`} v={money(ytd)} s={lastYearSame ? `${ytd >= lastYearSame ? "▲" : "▼"} ${money(Math.abs(ytd - lastYearSame))} vs same time last year` : `about ${money(ytd / monthsSoFar)} a month`} />
        <Stat k="Best month" v={best ? money(best[1]) : "—"} s={best ? `${MON[Number(best[0].slice(5)) - 1]} ${best[0].slice(0, 4)}` : undefined} />
        <Stat k="Scheduled to come in" v={money(ahead)} s="unpaid installments from this month on" />
        <Stat k="Booking rate (12 months)" v={inq12 ? `${Math.round((won12 / inq12) * 100)}%` : "—"} s={`${won12} booked of ${inq12} inquiries`} />{/* leak-check: allow: the app word "inquiry", not client data */}
      </div>
      <Section title="Money by month">
        <BarChart title="Money in" kind="money-stack" legend={["Received", "Scheduled"]} bars={moneyBars} highlight={9}
                  note="Solid = Zelle/payments received. Dashed = installments still due (overdue ones count in this month)." />
      </Section>
      <Section title="Inquiries and bookings">{/* leak-check: allow: the app word "inquiry", not client data */}
        <BarChart title="By the month they inquired" kind="pair" legend={["Inquiries", "Booked"]} bars={funnelBars} highlight={11} />{/* leak-check: allow: the app word "inquiry", not client data */}
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
