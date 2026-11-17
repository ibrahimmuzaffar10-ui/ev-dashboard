"use client";
import { useState } from "react";

// Small SVG bar charts for the Progress page. Colors come from validated tokens (--chart-1/--chart-2, light + dark,
// checked with the dataviz validator); text always uses ink tokens; every chart has hover/tap values, a legend when
// it has 2 series, and a "Show as table" view.
export type Bar = { label: string; sub?: string; a: number; b?: number };

const fmtMoney = (n: number) => n >= 1000 ? `$${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : `$${Math.round(n)}`;

export function BarChart({ title, bars, kind, legend, note, highlight }: {
  title: string; bars: Bar[]; kind: "money-stack" | "pair"; legend: [string, string]; note?: string; highlight?: number;
}) {
  const [hover, setHover] = useState<number | null>(highlight ?? null);
  const W = 340, H = 168, padL = 34, padB = 22, padT = 8;
  const top = Math.max(1, ...bars.map((b) => kind === "money-stack" ? b.a + (b.b || 0) : Math.max(b.a, b.b || 0)));
  const nice = (() => { const p = Math.pow(10, Math.floor(Math.log10(top))); const m = top / p; return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * p; })();
  const y = (v: number) => padT + (H - padT - padB) * (1 - v / nice);
  const slot = (W - padL) / bars.length, bw = Math.max(4, Math.min(18, slot * (kind === "pair" ? 0.34 : 0.6)));
  const fmt = (v: number) => kind === "money-stack" ? fmtMoney(v) : String(v);
  const h = hover !== null ? bars[hover] : null;
  return (
    <figure className="card p-4">
      <figcaption>
        <div className="font-semibold">{title}</div>
        <div className="text-[13px] tabular-nums text-[var(--ink)]" aria-live="polite">
          {h ? <><span className="text-[var(--muted)]">{h.label}{h.sub ? " " + h.sub : ""}:</span> {legend[0]} <b>{fmt(h.a)}</b>{h.b !== undefined ? <> · {legend[1]} <b>{fmt(h.b)}</b></> : null}</> : <span className="text-[var(--muted)]">Tap a bar for the numbers</span>}
        </div>
      </figcaption>
      <div className="mt-1 flex gap-3 text-[12px] text-[var(--muted)]">
        <span className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: kind === "pair" ? "var(--chart-2)" : "var(--chart-1)" }} />{legend[0]}</span>
        <span className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-sm" style={kind === "pair" ? { background: "var(--chart-1)" } : { border: "1.5px dashed var(--chart-1)" }} />{legend[1]}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 w-full" role="img" aria-label={title} onMouseLeave={() => setHover(highlight ?? null)}>
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={padL} x2={W} y1={y(nice * f)} y2={y(nice * f)} stroke="var(--line)" strokeWidth={1} />
            <text x={padL - 4} y={y(nice * f) + 3} textAnchor="end" fontSize={9} fill="var(--muted)">{fmt(nice * f)}</text>
          </g>
        ))}
        {bars.map((b, i) => {
          const cx = padL + slot * i + slot / 2, on = hover === i;
          const r = (x: number, v0: number, v1: number, fill: string, dashed = false) => {
            const yTop = y(v1), yBot = y(v0), hgt = Math.max(0, yBot - yTop - (v0 > 0 ? 2 : 0));
            if (v1 - v0 <= 0 || hgt <= 0) return null;
            return dashed
              ? <rect x={x} y={yTop} width={bw} height={hgt} rx={3} fill="none" stroke={fill} strokeWidth={1.5} strokeDasharray="3 2" />
              : <path d={`M${x},${yBot - (v0 > 0 ? 2 : 0)} V${yTop + 3} q0,-3 3,-3 h${bw - 6} q3,0 3,3 V${yBot - (v0 > 0 ? 2 : 0)} Z`} fill={fill} />;
          };
          return (
            <g key={i} opacity={hover === null || on ? 1 : 0.55}>
              {kind === "money-stack" ? <>{r(cx - bw / 2, 0, b.a, "var(--chart-1)")}{r(cx - bw / 2, b.a, b.a + (b.b || 0), "var(--chart-1)", true)}</>
                : <>{r(cx - bw - 1, 0, b.a, "var(--chart-2)")}{r(cx + 1, 0, b.b || 0, "var(--chart-1)")}</>}
              <text x={cx} y={H - 8} textAnchor="middle" fontSize={9} fill={on ? "var(--ink)" : "var(--muted)"}>{b.label.slice(0, 1)}</text>
              <rect x={cx - slot / 2} y={0} width={slot} height={H} fill="transparent" onMouseEnter={() => setHover(i)} onClick={() => setHover(i)} />
            </g>
          );
        })}
      </svg>
      {note && <p className="mt-1 text-[12px] text-[var(--muted)]">{note}</p>}
      <details className="mt-2 text-[13px]">
        <summary className="cursor-pointer text-[var(--accent)]">Show as table</summary>
        <table className="mt-2 w-full tabular-nums">
          <thead><tr className="text-left text-[var(--muted)]"><th className="font-normal">Month</th><th className="text-right font-normal">{legend[0]}</th><th className="text-right font-normal">{legend[1]}</th></tr></thead>
          <tbody>{bars.map((b, i) => <tr key={i} className="border-t border-[var(--line)]"><td>{b.label} {b.sub}</td><td className="text-right">{fmt(b.a)}</td><td className="text-right">{fmt(b.b || 0)}</td></tr>)}</tbody>
        </table>
      </details>
    </figure>
  );
}
