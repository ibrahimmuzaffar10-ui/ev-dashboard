// A lead still marked "needs reply" / "waiting" that isn't really waiting any more: its event date has passed,
// or nothing has happened on it for 45+ days. Used by the Leads "Stale" tab and to pre-pick a close reason.
import type { Lead } from "./data";

const daysBetween = (a: string, b: string) => Math.round((Date.parse(b) - Date.parse(a)) / 86400000);

export function staleWhy(l: Lead, today: string): { reason: string; text: string } | null {
  if (!["unanswered", "open"].includes(l.status)) return null;
  const days = l.days.map((d) => d.day).filter(Boolean) as string[];
  const last = days.sort().at(-1);
  if (last && last < today) return { reason: "date_passed", text: "Event date passed" };
  const touched = [l.lastContact, l.inquiry].filter(Boolean).sort().at(-1);  // leak-check: allow: the app field name "inquiry", not client data
  if (touched && daysBetween(touched, today) >= 45)
    return l.status === "open" ? { reason: "client_ghosted", text: `No reply from the client in ${daysBetween(touched, today)} days` }
                               : { reason: "no_reply_us", text: `Waiting on our reply for ${daysBetween(touched, today)} days` };
  return null;
}
