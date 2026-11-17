import Link from "next/link";
import { PageTitle } from "@/components/page-title";
import { NewLeadForm } from "./form";

export default function NewLead() {
  return (
    <>
      <div className="pt-3"><Link href="/leads" className="text-sm font-medium text-[var(--accent)]">‹ Leads</Link></div>
      <PageTitle title="New lead" sub="For inquiries from Instagram, a call or word of mouth" />
      <NewLeadForm />
    </>
  );
}
