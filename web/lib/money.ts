// Money rules shared by the Money page, Progress charts and each booking's page. Pure functions, no I/O.
//
// Cash basis: every payment counts in the month it ARRIVED, never the event month.
// A booking is "paid in full" once the money recorded on it reaches its total. Anything above the total is a tip.
// Chart colors per payment: green = the booking was paid off in that same month (all-in-one-month bookings, and the
// month the last payment landed); gold = a deposit or installment toward a booking still being paid off then.
import type { Lead, Payment } from "./data";

export type Ledger = {
  entries: { on: string | null; amount: number; sender: string | null; method: string | null; running: number; fullHere: boolean }[];
  total: number | null;       // agreed price (null = not set yet)
  linked: number;             // payments on file (Zelle etc.), with dates
  untracked: number;          // marked paid on the booking but with no payment on file (cash, before tracking…)
  paid: number;               // everything received
  left: number;               // still owed (0 when paid in full or no total)
  tip: number;                // received above the total
  complete: boolean;          // total set and reached
  completeMonth: string | null; // "YYYY-MM" of the payment that finished it (null when untracked money finished it)
};

const r2 = (n: number) => Math.round(n * 100) / 100;

export function ledger(l: Lead, pays: Payment[]): Ledger {
  const mine = pays.filter((p) => p.leadId === l.id && !p.personal).sort((a, b) => (a.on || "").localeCompare(b.on || ""));
  const linked = r2(mine.reduce((a, p) => a + p.amount, 0));
  const manual = l.paid ?? 0;
  const untracked = r2(Math.max(0, manual - linked));     // undated money is assumed to have come first
  const paid = r2(untracked + linked);
  const total = l.total && l.total > 0 ? l.total : null;
  let run = untracked, completeMonth: string | null = null, done = total !== null && untracked >= total - 0.005;
  const entries = mine.map((p) => {
    run = r2(run + p.amount);
    const fullHere = !done && total !== null && run >= total - 0.005;
    if (fullHere) { done = true; completeMonth = p.on?.slice(0, 7) || null; }
    return { on: p.on, amount: p.amount, sender: p.sender, method: p.method, running: run, fullHere };
  });
  const complete = total !== null && paid >= total - 0.005;
  return { entries, total, linked, untracked, paid, left: total === null ? 0 : r2(Math.max(0, total - paid)), tip: total === null ? 0 : r2(Math.max(0, paid - total)), complete, completeMonth };
}

// Money in per month, split green (paid off that month) / gold (partial). Business income without a booking is
// complete on arrival (green); a Zelle not matched yet counts as partial until it is sorted.
export function monthSplit(leads: Lead[], pays: Payment[]) {
  const out = new Map<string, { full: number; partial: number }>();
  const add = (ym: string | undefined, k: "full" | "partial", v: number) => {
    if (!ym) return; const m = out.get(ym) || { full: 0, partial: 0 }; m[k] += v; out.set(ym, m);
  };
  const done = new Map(leads.map((l) => [l.id, ledger(l, pays).completeMonth]));
  const finishedEarly = new Set(leads.filter((l) => { const g = ledger(l, pays); return g.complete && !g.completeMonth; }).map((l) => l.id));
  for (const p of pays) {
    if (p.personal) continue;
    const ym = p.on?.slice(0, 7);
    if (p.otherIncome) { add(ym, "full", p.amount); continue; }
    if (!p.leadId) { add(ym, "partial", p.amount); continue; }
    const cm = done.get(p.leadId);
    // green when this payment's month is the month the booking was paid off, or later (a tip after the final payment)
    add(ym, (cm && ym && ym >= cm) || finishedEarly.has(p.leadId) ? "full" : "partial", p.amount);
  }
  return out;
}
