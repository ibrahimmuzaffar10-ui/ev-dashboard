import Link from "next/link";
import { Suspense } from "react";
import { notFound } from "next/navigation";
import { loadContract, loadLeads } from "@/lib/data";
import { oldGet } from "@/lib/bridge";
import { SERVICE } from "@/components/ui";
import { PageTitle, Skeleton } from "@/components/page-title";
import { ContractForm } from "./form";

const WED = ["wedding", "multi_day_wedding", "nikkah", "walima", "mehndi", "baraat", "reception"];

async function Load({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [{ leads }, prior, opts] = await Promise.all([loadLeads(), loadContract(id), oldGet<{ privacy: string[] }>("/api/contract-options")]);
  const l = leads.find((x) => x.id === id);
  if (!l) notFound();
  const f = prior?.fields || {};
  const sv = l.service || "";
  // same defaults as the dashboard's form
  const init: Record<string, string> = {
    photographers: "1", addons: "None", travel_fee: "Included (Greater Houston)", ...f,
    client_names: f.client_names || l.client, client_email: f.client_email || l.email || "", locations: f.locations || l.venue || "",
    session_type: f.session_type || (SERVICE[sv] || ""),
    total: String(prior?.total ?? l.total ?? ""), retainer: String(prior?.retainer ?? (WED.includes(sv) ? 500 : sv === "graduation" ? 75 : 100)),
  };
  const days0 = l.days.length ? l.days.map((d) => ({ event: d.label || "", date: d.day || "", start: d.start || "", end: d.end || "", hours: "" })) : [];
  return (
    <>
      <PageTitle title={prior ? "Re-create contract" : "Create contract"} sub={l.client} />
      {prior && <p className="mt-2 rounded-xl px-3 py-2 text-[13px]" style={{ background: "var(--amber-bg)", color: "var(--amber)" }}>A contract already exists{prior.signed ? " and is signed" : ""}. Making a new one replaces the draft.</p>}
      <ContractForm id={id} client={l.client} init={init} days0={days0} privacy={opts?.privacy?.length ? opts.privacy : ["Standard usage"]} />
    </>
  );
}

export default function ContractPage(props: PageProps<"/leads/[id]/contract">) {
  return (
    <>
      <Suspense fallback={<Skeleton />}><BackLink params={props.params as Promise<{ id: string }>} /></Suspense>
      <Suspense fallback={<Skeleton />}><Load params={props.params as Promise<{ id: string }>} /></Suspense>
    </>
  );
}

async function BackLink({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <div className="pt-3"><Link href={`/leads/${id}`} className="text-sm font-medium text-[var(--accent)]">‹ Back</Link></div>;
}
