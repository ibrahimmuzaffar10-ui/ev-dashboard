"use client";
import { useMemo, useState, useTransition } from "react";
import Link from "next/link";
import { createContract, type ContractBody, type Result } from "../../actions";

type Day = ContractBody["days"][number];
type Plan = { label: string; amount: string; due: string };
const input = "w-full rounded-xl border border-[var(--line)] bg-[var(--bg)] px-3 py-2.5 text-[15px] text-[var(--ink)]";
const small = "w-full rounded-lg border border-[var(--line)] bg-[var(--bg)] px-2 py-2 text-[14px] text-[var(--ink)]";
const num = (v: string) => Number(String(v).replace(/[$,\s]/g, ""));
const minus = (iso: string, n: number) => { const d = new Date(iso + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() - n); return d.toISOString().slice(0, 10); };

export function ContractForm({ id, client, init, days0, privacy }: {
  id: string; client: string; init: Record<string, string>; days0: Day[]; privacy: string[];
}) {
  const [f, setF] = useState<Record<string, string>>(init);
  const [days, setDays] = useState<Day[]>([...days0, ...Array(Math.max(0, 2 - days0.length)).fill(0).map(() => ({ event: "", date: "", start: "", end: "", hours: "" }))].slice(0, 4));
  const [plan, setPlan] = useState<Plan[]>(() => {
    const empty = [{ label: "", amount: "", due: "" }, { label: "", amount: "", due: "" }, { label: "", amount: "", due: "" }];
    const d0 = days0.map((d) => d.date).filter(Boolean).sort()[0], tot = num(init.total || ""), ret = num(init.retainer || "");
    if (!tot || !d0 || Number.isNaN(ret)) return empty;
    const bal = tot - ret, h1 = Math.round(bal / 2);
    return [{ label: "50% of balance", amount: String(h1), due: minus(d0, 14) }, { label: "Final balance", amount: String(bal - h1), due: minus(d0, 1) }, empty[2]];
  });
  const [msg, setMsg] = useState<Result | null>(null);
  const [pending, start] = useTransition();
  const set = (k: string, v: string) => setF((x) => ({ ...x, [k]: v }));
  const first = useMemo(() => days.map((d) => d.date).filter(Boolean).sort()[0], [days]);
  // same rule as the dashboard: balance split 50% (2 weeks before) + final (1 day before), only while the plan is empty
  const autoSplit = (tot = f.total, ret = f.retainer, d0 = first) => {
    if (plan.some((p) => p.amount) || !num(tot) || !d0 || Number.isNaN(num(ret))) return;
    const bal = num(tot) - num(ret), h1 = Math.round(bal / 2);
    setPlan([{ label: "50% of balance", amount: String(h1), due: minus(d0, 14) }, { label: "Final balance", amount: String(bal - h1), due: minus(d0, 1) }, { label: "", amount: "", due: "" }]);
  };
  const T = (k: string, label: string, ph = "", full = true) => (
    <label className={"block text-sm text-[var(--muted)]" + (full ? "" : "")}>{label}<input value={f[k] || ""} placeholder={ph} onChange={(e) => set(k, e.target.value)} className={input + " mt-1"} /></label>
  );
  const submit = () => {
    if (!f.client_names?.trim()) return setMsg({ ok: false, msg: "Client name(s) on the contract are required" });
    if (!num(f.total) || Number.isNaN(num(f.retainer))) return setMsg({ ok: false, msg: "Enter the total and the retainer" });
    const fields = Object.fromEntries(["client_names", "first_names", "client_phone", "client_email", "client_address", "session_type", "city_state", "locations", "day_of_contact",
      "package_name", "image_estimate", "coverage_hours", "photographers", "inclusions", "addons", "privacy_option", "travel_fee"].map((k) => [k, (f[k] || (k === "privacy_option" ? privacy[0] : "")).trim()]));
    start(async () => setMsg(await createContract({ id, fields, total: num(f.total), retainer: num(f.retainer),
      days: days.filter((d) => d.date), plan: plan.filter((p) => p.amount).map((p) => ({ ...p, amount: num(p.amount) })) })));
  };
  if (msg?.ok) return (
    <div className="card mt-4 space-y-3 p-5 text-center">
      <div className="text-3xl">📄</div><p className="font-medium">{msg.msg}</p>
      <p className="text-sm text-[var(--muted)]">Next: Eman reviews it, uploads the PDF to DocuSeal and sends it; then set Contract → Sent.</p>
      <Link href={`/leads/${id}`} className="btn btn-primary w-full">Back to {client}</Link>
    </div>
  );
  return (
    <div className="mt-4 space-y-4 pb-4">
      <div className="card space-y-3 p-4">
        <h2 className="font-semibold">Client</h2>
        {T("client_names", "Name(s) on the contract *")}{T("first_names", "First names (file name)", "e.g. Sara & Ali")}
        <div className="grid grid-cols-2 gap-3">{T("client_phone", "Phone")}{T("client_email", "Email")}</div>
        {T("client_address", "Mailing address")}
      </div>
      <div className="card space-y-3 p-4">
        <h2 className="font-semibold">Event</h2>
        {T("session_type", "Event / session type", "Multi-day wedding (Mehndi + Nikkah)")}{T("locations", "Location(s)")}
        <div className="grid grid-cols-2 gap-3">{T("city_state", "City, State", "if outside Houston")}{T("day_of_contact", "Day-of contact")}</div>
        <div className="space-y-2">
          <div className="text-sm text-[var(--muted)]">Event days</div>
          {days.map((d, i) => (
            <div key={i} className="grid grid-cols-6 gap-1.5 rounded-xl bg-[var(--panel-2)] p-2">
              <input className={small + " col-span-3"} placeholder="Nikkah" value={d.event} onChange={(e) => setDays(days.map((x, j) => j === i ? { ...x, event: e.target.value } : x))} />
              <input className={small + " col-span-3"} type="date" value={d.date} onChange={(e) => { const n = days.map((x, j) => j === i ? { ...x, date: e.target.value } : x); setDays(n); autoSplit(f.total, f.retainer, n.map((x) => x.date).filter(Boolean).sort()[0]); }} />
              <input className={small + " col-span-2"} placeholder="4:00 PM" value={d.start} onChange={(e) => setDays(days.map((x, j) => j === i ? { ...x, start: e.target.value } : x))} />
              <input className={small + " col-span-2"} placeholder="10:00 PM" value={d.end} onChange={(e) => setDays(days.map((x, j) => j === i ? { ...x, end: e.target.value } : x))} />
              <input className={small + " col-span-2"} placeholder="hours" value={d.hours} onChange={(e) => setDays(days.map((x, j) => j === i ? { ...x, hours: e.target.value } : x))} />
            </div>
          ))}
          {days.length < 4 && <button className="btn w-full" onClick={() => setDays([...days, { event: "", date: "", start: "", end: "", hours: "" }])}>+ Another day</button>}
        </div>
      </div>
      <div className="card space-y-3 p-4">
        <h2 className="font-semibold">Package</h2>
        <div className="grid grid-cols-2 gap-3">{T("package_name", "Package")}{T("image_estimate", "Estimated images")}</div>
        <div className="grid grid-cols-2 gap-3">{T("coverage_hours", "Coverage hours (total)")}{T("photographers", "Photographers")}</div>
        {T("inclusions", "Included", "Inspiration board, timeline coordination…")}
        <div className="grid grid-cols-2 gap-3">{T("addons", "Add-ons")}
          <label className="block text-sm text-[var(--muted)]">Privacy package
            <select value={f.privacy_option || privacy[0]} onChange={(e) => set("privacy_option", e.target.value)} className={input + " mt-1"}>{privacy.map((p) => <option key={p}>{p}</option>)}</select>
          </label>
        </div>
        {T("travel_fee", "Travel fee")}
      </div>
      <div className="card space-y-3 p-4">
        <h2 className="font-semibold">Price</h2>
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-sm text-[var(--muted)]">TOTAL ($) *<input inputMode="decimal" value={f.total || ""} onChange={(e) => set("total", e.target.value)} onBlur={() => autoSplit()} className={input + " mt-1"} /></label>
          <label className="block text-sm text-[var(--muted)]">Retainer ($) *<input inputMode="decimal" value={f.retainer || ""} onChange={(e) => set("retainer", e.target.value)} onBlur={() => autoSplit()} className={input + " mt-1"} /></label>
        </div>
        <div className="text-sm text-[var(--muted)]">Payment plan for the balance (up to 3)</div>
        {plan.map((p, i) => (
          <div key={i} className="grid grid-cols-6 gap-1.5">
            <input className={small + " col-span-3"} placeholder="Label" value={p.label} onChange={(e) => setPlan(plan.map((x, j) => j === i ? { ...x, label: e.target.value } : x))} />
            <input className={small + " col-span-1"} inputMode="decimal" placeholder="$" value={p.amount} onChange={(e) => setPlan(plan.map((x, j) => j === i ? { ...x, amount: e.target.value } : x))} />
            <input className={small + " col-span-2"} type="date" value={p.due} onChange={(e) => setPlan(plan.map((x, j) => j === i ? { ...x, due: e.target.value } : x))} />
          </div>
        ))}
      </div>
      {msg && !msg.ok && <p role="alert" className="text-center text-sm text-[var(--red)]">{msg.msg}</p>}
      <button className="btn btn-primary w-full py-3 text-base" disabled={pending} onClick={submit}>{pending ? "Making the contract… (up to 30 s)" : "Create & email draft to Eman"}</button>
      <p className="text-center text-xs text-[var(--muted)]">Same template as the dashboard. Sign-by date = 7 days from today.</p>
    </div>
  );
}
