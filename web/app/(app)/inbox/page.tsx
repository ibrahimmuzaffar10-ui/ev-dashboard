import { Suspense } from "react";
import { loadAlerts, loadLeads, todayCT } from "@/lib/data";
import { extractFacts } from "@/lib/facts";
import { Empty } from "@/components/ui";
import { PageTitle, Skeleton } from "@/components/page-title";
import { AlertCard, type CardData } from "./alert-card";

const KIND: Record<string, [string, string]> = {
  new_inquiry: ["Website form", "amber"], possible_inquiry: ["Possible inquiry", "amber"], unclear: ["Unclear message", "grey"],  // leak-check: allow: the app word "inquiry", not client data
  client_email: ["Client email", "blue"], payment: ["Zelle payment", "green"], contract_signed: ["Contract signed", "green"],
  reminder: ["Reminder", "red"], email: ["Email", "grey"],
};

function when(at: string | null, today: string) {
  if (!at) return "";
  const dt = new Date(at);                                       // stored with its time zone; shown in Houston time
  const d = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Chicago" }).format(dt);
  if (d === today) return dt.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/Chicago" });
  return dt.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "America/Chicago" });
}

async function List() {
  const today = await todayCT();
  const [{ alerts, error }, { leads }] = await Promise.all([loadAlerts(), loadLeads()]);
  if (error) return <Empty>Couldn&apos;t load: {error}</Empty>;
  if (!alerts.length) return <Empty>Inbox zero. New inquiries, client replies and payments show up here.</Empty>;  // leak-check: allow: the app word "inquiry", not client data
  const byId = new Map(leads.map((l) => [l.id, l]));
  const cards: CardData[] = alerts.map((a) => {
    const [kind, tone] = KIND[a.type] || [a.type, "grey"];
    const who = a.title.includes(": ") ? a.title.split(": ").slice(1).join(": ").replace(/ \(in Junk!\)/, "") : a.title;
    const lead = a.leadId ? byId.get(a.leadId) : undefined;
    return {
      id: a.id, kind: kind + (a.title.includes("(in Junk!)") ? " · found in Junk" : ""), tone, who: lead?.client || who, when: when(a.at, today),
      fromEmail: a.fromEmail, leadId: a.leadId, leadName: lead && lead.client !== who ? lead.client : null, subject: a.detail.split(" — ")[0].split("\n")[0].slice(0, 120),
      facts: extractFacts(a.title, a.detail), count: a.count, isPerson: !["payment", "contract_signed", "reminder"].includes(a.type),
    };
  });
  return <div className="mt-4 space-y-3">{cards.map((c) => <AlertCard key={c.id} a={c} />)}</div>;
}

export default function Inbox() {
  return (
    <>
      <PageTitle title="Inbox" sub="Inquiries, client replies and payments" />{/* leak-check: allow: the app word "inquiry", not client data */}
      <Suspense fallback={<Skeleton />}><List /></Suspense>
    </>
  );
}
