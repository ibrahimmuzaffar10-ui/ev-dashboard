"use client";
import { useEffect, useRef, useState } from "react";

// Scrollable monthly bar chart for the Progress page. One bar per month (stacked segments, or a pair side by side).
// Colors are validated tokens (--chart-1/2/3, light + dark); text always uses ink tokens.
// Tap/hover a colored segment → just that segment's number. Tap the month anywhere else → the month's total.
// Swipe sideways for older months; a line + the year marks where each new year starts; the year of the leftmost
// month sits bottom-left. Legend + "Show as table" so color is never the only way to read it.
export type Series = { name: string; color: string; dashed?: boolean };
export type Bar = { ym: string; v: number[] };

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const label = (ym: string) => `${MON[Number(ym.slice(5)) - 1]} ${ym.slice(0, 4)}`;
const usd = (n: number) => n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const short = (n: number) => n >= 1000 ? `$${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : `$${Math.round(n)}`;

export function BarChart({ title, series, bars, layout, money, note, focus }: {
  title: string; series: Series[]; bars: Bar[]; layout: "stack" | "pair"; money: boolean; note?: string; focus: number;
}) {
  const [sel, setSel] = useState<{ i: number; s: number | null }>({ i: focus, s: null });
  const [leftYear, setLeftYear] = useState(bars[0]?.ym.slice(0, 4) || "");
  const box = useRef<HTMLDivElement>(null);
  const SLOT = 46, H = 176, padT = 20, padB = 22, W = bars.length * SLOT;
  const fmt = (n: number) => money ? usd(n) : String(n);
  const solid = (b: Bar) => b.v.reduce((a, v, k) => a + (series[k].dashed ? 0 : v), 0);
  const top = Math.max(1, ...bars.map((b) => layout === "stack" ? b.v.reduce((a, v) => a + v, 0) : Math.max(...b.v)));
  const nice = (() => { const p = Math.pow(10, Math.floor(Math.log10(top))); const m = top / p; return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * p; })();
  const y = (v: number) => padT + (H - padT - padB) * (1 - v / nice);
  const bw = layout === "pair" ? 13 : 22;

  // start scrolled so the focus month (this month) and the next 2 are in view
  useEffect(() => {
    const el = box.current; if (!el) return;
    el.scrollLeft = Math.max(0, (focus + 1 + Math.min(2, bars.length - 1 - focus)) * SLOT - el.clientWidth);
    setLeftYear(bars[Math.floor(el.scrollLeft / SLOT)]?.ym.slice(0, 4) || "");
  }, [focus, bars]);
  const onScroll = () => { const el = box.current; if (el) setLeftYear(bars[Math.min(bars.length - 1, Math.floor((el.scrollLeft + 4) / SLOT))]?.ym.slice(0, 4) || ""); };

  const b = bars[sel.i];
  const readout = !b ? null : sel.s !== null
    ? <><span className="text-[var(--muted)]">{label(b.ym)} · {series[sel.s].name}:</span> <b>{fmt(b.v[sel.s])}</b></>
    : layout === "stack"
      ? <><span className="text-[var(--muted)]">{label(b.ym)} · Total received:</span> <b>{fmt(solid(b))}</b>{series.map((s, k) => s.dashed && b.v[k] ? <span key={k} className="text-[var(--muted)]"> · {fmt(b.v[k])} {s.name.toLowerCase()}</span> : null)}</>
      : <><span className="text-[var(--muted)]">{label(b.ym)}:</span> {series.map((s, k) => <span key={k}>{k ? " · " : ""}{s.name} <b>{fmt(b.v[k])}</b></span>)}</>;

  const seg = (i: number, k: number, x: number, v0: number, v1: number, w: number) => {
    const s = series[k], gap = v0 > 0 ? 2 : 0, yTop = y(v1), yBot = y(v0) - gap, hgt = yBot - yTop;
    if (v1 - v0 <= 0 || hgt <= 0.5) return null;
    const on = sel.i === i && sel.s === k, dim = sel.i === i && sel.s !== null && !on;
    const pick = (e: React.SyntheticEvent) => { e.stopPropagation(); setSel({ i, s: k }); };
    const hitH = Math.max(hgt, 14);
    return (
      <g key={k} opacity={dim ? 0.45 : 1}>
        {s.dashed
          ? <rect x={x + 0.75} y={yTop + 0.75} width={w - 1.5} height={Math.max(0, hgt - 1.5)} rx={3} fill="none" stroke={s.color} strokeWidth={1.5} strokeDasharray="3 2" />
          : <path d={`M${x},${yBot} V${yTop + Math.min(4, hgt)} q0,-${Math.min(4, hgt)} 4,-${Math.min(4, hgt)} h${w - 8} q4,0 4,${Math.min(4, hgt)} V${yBot} Z`} fill={s.color} />}
        {on && <rect x={x - 2} y={yTop - 2} width={w + 4} height={hgt + 4} rx={4} fill="none" stroke="var(--ink)" strokeWidth={1.5} />}
        <rect x={x - 4} y={yTop - (hitH - hgt) / 2} width={w + 8} height={hitH} fill="transparent" style={{ cursor: "pointer" }}
              onClick={pick} onMouseEnter={pick} onMouseLeave={() => setSel({ i, s: null })}><title>{`${label(bars[i].ym)} · ${s.name}: ${fmt(bars[i].v[k])}`}</title></rect>
      </g>
    );
  };

  return (
    <figure className="card p-4">
      <figcaption>
        <div className="font-semibold">{title}</div>
        <div className="min-h-[20px] text-[13px] tabular-nums text-[var(--ink)]" aria-live="polite">{readout}</div>
      </figcaption>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-[var(--muted)]">
        {series.map((s, k) => <span key={k} className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-sm" style={s.dashed ? { border: `1.5px dashed ${s.color}` } : { background: s.color }} />{s.name}</span>)}
      </div>
      <div className="mt-2 flex">
        <svg width={38} height={H} className="shrink-0" aria-hidden>
          {[0, 0.5, 1].map((f) => <text key={f} x={34} y={y(nice * f) + 3} textAnchor="end" fontSize={10} fill="var(--muted)">{money ? short(nice * f) : nice * f}</text>)}
        </svg>
        <div ref={box} onScroll={onScroll} className="min-w-0 flex-1 overflow-x-auto overscroll-x-contain" style={{ scrollbarWidth: "thin" }}>
          <svg width={W} height={H} role="img" aria-label={`${title}, ${label(bars[0]?.ym || "")} to ${label(bars[bars.length - 1]?.ym || "")}`} className="block">
            {[0, 0.5, 1].map((f) => <line key={f} x1={0} x2={W} y1={y(nice * f)} y2={y(nice * f)} stroke="var(--line)" strokeWidth={1} />)}
            {bars.map((bar, i) => {
              const x0 = i * SLOT, cx = x0 + SLOT / 2, isSel = sel.i === i, newYear = bar.ym.endsWith("-01") && i > 0;
              let acc = 0;
              return (
                <g key={bar.ym}>
                  <rect x={x0} y={0} width={SLOT} height={H} fill={isSel ? "var(--panel-2)" : "transparent"} onClick={() => setSel({ i, s: null })} onMouseEnter={() => sel.s === null && setSel({ i, s: null })} />
                  {newYear && <><line x1={x0} x2={x0} y1={4} y2={H - 4} stroke="var(--muted)" strokeWidth={1} strokeDasharray="2 3" />
                    <text x={x0 + 4} y={12} fontSize={10} fontWeight={600} fill="var(--ink)">{bar.ym.slice(0, 4)}</text></>}
                  {layout === "stack"
                    ? bar.v.map((v, k) => { const s0 = acc; acc += v; return seg(i, k, cx - bw / 2, s0, acc, bw); })
                    : bar.v.map((v, k) => seg(i, k, cx - bw - 1 + k * (bw + 2), 0, v, bw))}
                  <text x={cx} y={H - 7} textAnchor="middle" fontSize={11} fontWeight={isSel ? 700 : 400} fill={isSel ? "var(--ink)" : "var(--muted)"} style={{ pointerEvents: "none" }}>{MON[Number(bar.ym.slice(5)) - 1]}</text>
                </g>
              );
            })}
          </svg>
        </div>
      </div>
      <div className="mt-1 flex items-center justify-between text-[12px] text-[var(--muted)]">
        <span className="font-semibold text-[var(--ink)]">{leftYear}</span>
        {bars.length * SLOT > 300 && <span>‹ swipe for older months</span>}
      </div>
      {note && <p className="mt-1 text-[12px] text-[var(--muted)]">{note}</p>}
      <details className="mt-2 text-[13px]">
        <summary className="cursor-pointer text-[var(--accent)]">Show as table</summary>
        <div className="overflow-x-auto">
          <table className="mt-2 w-full tabular-nums">
            <thead><tr className="text-left text-[var(--muted)]"><th className="font-normal">Month</th>{series.map((s) => <th key={s.name} className="text-right font-normal">{s.name}</th>)}{layout === "stack" && <th className="text-right font-normal">Received</th>}</tr></thead>
            <tbody>{[...bars].reverse().map((bar) => <tr key={bar.ym} className="border-t border-[var(--line)]"><td>{label(bar.ym)}</td>{bar.v.map((v, k) => <td key={k} className="text-right">{fmt(v)}</td>)}{layout === "stack" && <td className="text-right font-semibold">{fmt(solid(bar))}</td>}</tr>)}</tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
