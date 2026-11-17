// Small shared pieces: status pill, money, dates. Server-safe (no hooks).
export const STATUS: Record<string, { label: string; tone: string }> = {
  unanswered: { label: "Needs reply", tone: "amber" }, open: { label: "Waiting on client", tone: "blue" },
  booked: { label: "Booked", tone: "green" }, completed: { label: "Completed", tone: "green" },
  ghosted: { label: "Ghosted", tone: "grey" }, lost: { label: "Lost", tone: "grey" },
};

export function Pill({ tone, children }: { tone: string; children: React.ReactNode }) {
  return <span className="chip font-medium" style={{ background: `var(--${tone}-bg)`, color: `var(--${tone})` }}>{children}</span>;
}

export function StatusPill({ status }: { status: string }) {
  const s = STATUS[status] || { label: status, tone: "grey" };
  return <Pill tone={s.tone}>{s.label}</Pill>;
}

export const money = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export function day(iso: string | null | undefined, opts: Intl.DateTimeFormatOptions = { weekday: "short", month: "short", day: "numeric" }) {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-US", { ...opts, timeZone: "UTC" });
}

export function daysFrom(today: string, iso: string) {
  const a = Date.parse(today.slice(0, 10) + "T00:00:00Z"), b = Date.parse(iso.slice(0, 10) + "T00:00:00Z");
  return Math.round((b - a) / 86400000);
}

export function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <div className="mb-2 flex items-baseline justify-between px-1">
        <h2 className="text-[13px] font-semibold uppercase tracking-wide text-[var(--muted)]">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="card px-4 py-6 text-center text-sm text-[var(--muted)]">{children}</div>;
}

export const SERVICE: Record<string, string> = {
  wedding: "Wedding", multi_day_wedding: "Multi-day wedding", nikkah: "Nikkah", walima: "Walima", mehndi: "Mehndi",
  engagement_couples: "Engagement / couples", family: "Family", graduation: "Graduation", maternity: "Maternity", event_other: "Event",
};
export const serviceLabel = (s: string | null | undefined) => (!s || s === "unknown" ? null : SERVICE[s] || s.replace(/_/g, " "));
