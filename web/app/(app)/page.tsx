import Link from "next/link";
import { Suspense } from "react";
import { loadAlerts, loadLeads, loadMoney, todayCT } from "@/lib/data";
import { supabaseServer } from "@/lib/supabase/server";
import { Empty, Pill, Section, day, daysFrom, money } from "@/components/ui";
import { PageTitle, Skeleton } from "@/components/page-title";
import { logout } from "../login/actions";

function Attn({ href, n, label, tone }: { href: string; n: number; label: string; tone: string }) {
  return (
    <Link href={href} className="card flex items-center gap-3 p-4 active:scale-[.99]">
      <span className="flex h-10 min-w-10 items-center justify-center rounded-xl px-2 text-lg font-semibold tabular-nums"
            style={{ background: `var(--${tone}-bg)`, color: `var(--${tone})` }}>{n}</span>
      <span className="flex-1 text-[15px] font-medium">{label}</span>
      <span className="text-[var(--muted)]">›</span>
    </Link>
  );
}

async function Today() {
  const today = await todayCT();
  const [{ leads, error }, { alerts }, { inst }] = await Promise.all([loadLeads(), loadAlerts(), loadMoney()]);
  if (error) return <Empty>Couldn&apos;t load data: {error}</Empty>;
  const byId = new Map(leads.map((l) => [l.id, l]));
  const needsReply = leads.filter((l) => l.status === "unanswered").length;
  const calls = leads.filter((l) => l.call === "booked" && l.callOn && daysFrom(today, l.callOn) >= 0 && daysFrom(today, l.callOn) <= 1);
  const dueSoon = inst.filter((i) => !i.paid && i.due && daysFrom(today, i.due) <= 7);
  const overdue = dueSoon.filter((i) => daysFrom(today, i.due!) < 0);
  const shoots = leads.filter((l) => l.status === "booked").flatMap((l) => l.days.filter((d) => d.day && daysFrom(today, d.day) >= 0 && daysFrom(today, d.day) <= 30).map((d) => ({ l, d })))
    .sort((a, b) => a.d.day!.localeCompare(b.d.day!));
  const upcomingBooked = new Set(leads.filter((l) => l.status === "booked" && l.days.some((d) => d.day && d.day >= today)).map((l) => l.id)).size;
  const hour = Number(new Intl.DateTimeFormat("en-US", { timeZone: "America/Chicago", hour: "numeric", hour12: false }).format(new Date()));
  const hello = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

  return (
    <>
      <PageTitle title={hello} sub={day(today, { weekday: "long", month: "long", day: "numeric" })} />
      <div className="mt-4 space-y-2.5">
        {alerts.length > 0 && <Attn href="/inbox" n={alerts.length} label={alerts.length === 1 ? "new message to look at" : "new messages to look at"} tone="red" />}
        {needsReply > 0 && <Attn href="/leads?f=reply" n={needsReply} label={needsReply === 1 ? "lead waiting on our reply" : "leads waiting on our reply"} tone="amber" />}
        {calls.length > 0 && <Attn href="/leads?f=calls" n={calls.length} label="15-min calls today / tomorrow" tone="green" />}
        {overdue.length > 0 && <Attn href="/money" n={overdue.length} label={overdue.length === 1 ? "payment overdue" : "payments overdue"} tone="red" />}
        {dueSoon.length - overdue.length > 0 && <Attn href="/money" n={dueSoon.length - overdue.length} label="payments due this week" tone="amber" />}
        {!alerts.length && !needsReply && !calls.length && !dueSoon.length && <Empty>All caught up. Nothing needs you right now.</Empty>}
      </div>

      <div className="mt-6 grid grid-cols-3 gap-2.5">
        {[["Waiting on client", leads.filter((l) => l.status === "open").length], ["Upcoming bookings", upcomingBooked], ["Calls offered", leads.filter((l) => l.call === "offered").length]].map(([k, v]) => (
          <div key={k as string} className="card p-3">
            <div className="text-2xl font-semibold tabular-nums">{v}</div>
            <div className="text-[12px] leading-tight text-[var(--muted)]">{k}</div>
          </div>
        ))}
      </div>

      <Section title="Shoots in the next 30 days" action={<Link href="/calendar" className="text-sm font-medium text-[var(--accent)]">Calendar</Link>}>
        {shoots.length ? (
          <ul className="card divide-y divide-[var(--line)]">
            {shoots.slice(0, 6).map(({ l, d }, i) => {
              const n = daysFrom(today, d.day!);
              return (
                <li key={i}>
                  <Link href={`/leads/${l.id}`} className="flex items-center gap-3 px-4 py-3">
                    <div className="w-12 text-center">
                      <div className="text-[11px] font-semibold uppercase text-[var(--accent)]">{day(d.day, { month: "short" })}</div>
                      <div className="text-xl font-semibold leading-none tabular-nums">{Number(d.day!.slice(8, 10))}</div>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium">{l.client}</div>
                      <div className="truncate text-sm text-[var(--muted)]">{[d.label, d.start && d.end ? `${d.start}–${d.end}` : d.start, d.venue || l.venue].filter(Boolean).join(" · ") || "Details in the lead"}</div>
                    </div>
                    <span className="text-xs text-[var(--muted)]">{n === 0 ? "today" : n === 1 ? "tomorrow" : `in ${n} d`}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        ) : <Empty>No shoots in the next 30 days.</Empty>}
      </Section>

      {dueSoon.length > 0 && (
        <Section title="Payments due">
          <ul className="card divide-y divide-[var(--line)]">
            {dueSoon.slice(0, 5).map((i, k) => (
              <li key={k} className="flex items-center gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{byId.get(i.leadId)?.client || i.leadId}</div>
                  <div className="text-sm text-[var(--muted)]">{i.label || "Installment"} · {day(i.due)}</div>
                </div>
                <div className="text-right">
                  <div className="font-semibold tabular-nums">{money(i.amount)}</div>
                  {daysFrom(today, i.due!) < 0 && <Pill tone="red">Overdue</Pill>}
                </div>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </>
  );
}

async function Footer() {
  const sb = await supabaseServer();
  const { data: { user } } = process.env.EV_DEMO === "1" && !process.env.VERCEL ? { data: { user: { email: "demo preview" } } } : await sb.auth.getUser();
  return (
    <footer className="mt-10 space-y-3 text-center text-xs text-[var(--muted)]">
      <div className="flex justify-center gap-4">
        <Link href="/vendors" className="underline-offset-2 hover:underline">Vendors</Link>
        <a href="https://ev-dashboard-tan.vercel.app" className="underline-offset-2 hover:underline">Full dashboard</a>
      </div>
      <form action={logout}>Signed in as {user?.email} · <button className="underline">Sign out</button></form>
    </footer>
  );
}

export default function Home() {
  return (
    <>
      <Suspense fallback={<><PageTitle title="Today" /><Skeleton /></>}><Today /></Suspense>
      <Suspense fallback={null}><Footer /></Suspense>
    </>
  );
}
