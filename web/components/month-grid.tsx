"use client";
import Link from "next/link";
import { useMemo, useState } from "react";

export type CalEvent = { date: string; client: string; label: string | null; time: string | null; booked: boolean; leadId: string };

const WD = ["S", "M", "T", "W", "T", "F", "S"];
const first = (s: string) => s.replace(/^TEST\s+/, "TEST ").split(/[ &]/)[0];

// Month view: booked = solid emerald, held date (open enquiry) = dashed blue; the client's name is on the day.
export function MonthGrid({ events, today }: { events: CalEvent[]; today: string }) {
  const [ym, setYm] = useState(today.slice(0, 7));
  const [picked, setPicked] = useState<string | null>(null);
  const byDay = useMemo(() => { const m = new Map<string, CalEvent[]>(); for (const e of events) m.set(e.date, [...(m.get(e.date) || []), e]); return m; }, [events]);
  const [y, m] = ym.split("-").map(Number);
  const startWd = new Date(Date.UTC(y, m - 1, 1)).getUTCDay(), days = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const cells = [...Array(startWd).fill(null), ...Array.from({ length: days }, (_, i) => `${ym}-${String(i + 1).padStart(2, "0")}`)];
  const move = (n: number) => { const d = new Date(Date.UTC(y, m - 1 + n, 1)); setYm(d.toISOString().slice(0, 7)); setPicked(null); };
  const title = new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" });
  const list = picked ? byDay.get(picked) || [] : [];
  return (
    <section className="card mt-4 p-3">
      <div className="flex items-center justify-between px-1 pb-2">
        <button className="btn !min-h-9 !px-3" onClick={() => move(-1)} aria-label="Previous month">‹</button>
        <h2 className="font-serif text-lg font-semibold">{title}</h2>
        <button className="btn !min-h-9 !px-3" onClick={() => move(1)} aria-label="Next month">›</button>
      </div>
      <div className="grid grid-cols-7 gap-1 text-center text-[11px] text-[var(--muted)]">{WD.map((d, i) => <div key={i}>{d}</div>)}</div>
      <div className="mt-1 grid grid-cols-7 gap-1">
        {cells.map((d, i) => {
          if (!d) return <div key={i} />;
          const evs = byDay.get(d) || [], isToday = d === today, sel = d === picked;
          return (
            <button key={d} onClick={() => setPicked(sel ? null : d)} aria-label={`${d}: ${evs.length} event${evs.length === 1 ? "" : "s"}`}
                    className="flex min-h-[58px] flex-col items-stretch gap-0.5 rounded-lg p-1 text-left"
                    style={{ background: sel ? "var(--accent-soft)" : "var(--bg)", outline: isToday ? "1.5px solid var(--accent)" : "none" }}>
              <span className="text-[11px] tabular-nums" style={{ color: isToday ? "var(--accent)" : "var(--muted)", fontWeight: isToday ? 700 : 400 }}>{Number(d.slice(8))}</span>
              {evs.slice(0, 2).map((e, k) => (
                <span key={k} className="truncate rounded px-1 text-[10px] leading-[15px]"
                      style={e.booked ? { background: "var(--chart-1)", color: "#fff" } : { border: "1px dashed var(--chart-2)", color: "var(--ink)" }}>
                  {first(e.client)}
                </span>
              ))}
              {evs.length > 2 && <span className="text-[10px] text-[var(--muted)]">+{evs.length - 2}</span>}
            </button>
          );
        })}
      </div>
      <div className="mt-2 flex gap-4 px-1 text-[12px] text-[var(--muted)]">
        <span className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: "var(--chart-1)" }} />Booked</span>
        <span className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-sm" style={{ border: "1.5px dashed var(--chart-2)" }} />Held (open inquiry)</span>{/* leak-check: allow: the app word "inquiry", not client data */}
      </div>
      {picked && (
        <ul className="mt-2 divide-y divide-[var(--line)] border-t border-[var(--line)]">
          {list.length ? list.map((e, k) => (
            <li key={k}><Link href={`/leads/${e.leadId}`} className="flex items-center justify-between gap-2 px-1 py-2.5">
              <span className="min-w-0"><span className="block truncate font-medium">{e.client}</span><span className="block truncate text-[13px] text-[var(--muted)]">{[e.label, e.time].filter(Boolean).join(" · ") || "—"}</span></span>
              <span className="text-[12px]" style={{ color: e.booked ? "var(--green)" : "var(--blue)" }}>{e.booked ? "Booked" : "Held"}</span>
            </Link></li>
          )) : <li className="px-1 py-2.5 text-[13px] text-[var(--muted)]">Nothing on this day.</li>}
        </ul>
      )}
    </section>
  );
}
