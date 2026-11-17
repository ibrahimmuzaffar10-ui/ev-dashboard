// Phase 12 home: proves phone login + reads through Row Level Security with the user's own session.
// (Phase 13 builds the real screens: Dashboard, Pipeline, Bookings, Calendar, Vendors, Financials.)
import { Suspense } from "react";
import { supabaseServer } from "@/lib/supabase/server";
import { logout } from "./login/actions";

type Tone = "green" | "yellow" | "orange" | "red";

function Tile({ label, value, tone }: { label: string; value: number | string; tone: Tone }) {
  return (
    <div className="rounded-2xl p-4" style={{ background: `var(--${tone}-bg)`, color: `var(--${tone})` }}>
      <div className="text-3xl font-semibold tabular-nums">{value}</div>
      <div className="text-sm opacity-90">{label}</div>
    </div>
  );
}

// Reads the session cookie at request time (never cached): streams in behind <Suspense>.
async function Dashboard() {
  const supabase = await supabaseServer();
  const { data: { user } } = await supabase.auth.getUser();
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Chicago" }).format(new Date());
  const [leads, alerts, days] = await Promise.all([
    supabase.from("leads").select("lead_id, status"),
    supabase.from("alerts").select("alert_id").eq("done", false),
    supabase.from("event_days").select("lead_id, day").gte("day", today),
  ]);
  const error = leads.error || alerts.error || days.error;
  const by = (s: string) => (leads.data || []).filter((l) => l.status === s).length;
  const booked = new Set((leads.data || []).filter((l) => l.status === "booked").map((l) => l.lead_id));
  const upcoming = (days.data || []).filter((d) => booked.has(d.lead_id)).length;

  return (
    <>
      {error ? (
        <p role="alert" className="rounded-xl bg-[var(--red-bg)] p-4 text-[var(--red)]">Couldn&apos;t load data: {error.message}</p>
      ) : (
        <section className="grid grid-cols-2 gap-3">
          <Tile label="Waiting on our reply" value={by("unanswered")} tone="orange" />
          <Tile label="Open alerts" value={(alerts.data || []).length} tone={(alerts.data || []).length ? "red" : "green"} />
          <Tile label="Open (waiting on client)" value={by("open")} tone="yellow" />
          <Tile label="Booked" value={by("booked")} tone="green" />
          <Tile label="Upcoming booked event days" value={upcoming} tone="green" />
          <Tile label="All leads" value={(leads.data || []).length} tone="yellow" />
        </section>
      )}
      <p className="mt-6 text-xs text-[var(--muted)]">Signed in as {user?.email}. New phone-first app (preview). The full dashboard is still at the main address.</p>
    </>
  );
}

export default function Home() {
  return (
    <main className="mx-auto max-w-xl px-4 pb-10 pt-[max(1rem,env(safe-area-inset-top))]">
      <header className="flex items-center justify-between py-3">
        <h1 className="text-xl font-semibold">Emanant HQ</h1>
        <form action={logout}>
          <button className="rounded-lg border border-[var(--line)] px-3 py-2 text-sm text-[var(--muted)]">Sign out</button>
        </form>
      </header>
      <Suspense fallback={<div className="grid grid-cols-2 gap-3">{Array.from({ length: 6 }, (_, i) => <div key={i} className="h-24 animate-pulse rounded-2xl bg-[var(--panel)]" />)}</div>}>
        <Dashboard />
      </Suspense>
    </main>
  );
}
