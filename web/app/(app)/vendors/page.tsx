import { Suspense } from "react";
import { loadVendors } from "@/lib/data";
import { Empty } from "@/components/ui";
import { PageTitle, Skeleton } from "@/components/page-title";

async function List() {
  const { vendors, error } = await loadVendors();
  if (error) return <Empty>Couldn&apos;t load: {error}</Empty>;
  if (!vendors.length) return <Empty>No vendors yet.</Empty>;
  return (
    <ul className="card mt-4 divide-y divide-[var(--line)]">
      {vendors.map((v) => (
        <li key={v.vendor_id} className="px-4 py-3">
          <div className="flex items-baseline justify-between gap-2"><span className="font-medium">{v.name}</span>{v.type && <span className="chip">{v.type}</span>}</div>
          {(v.note || v.channel) && <div className="text-sm text-[var(--muted)]">{[v.channel, v.note].filter(Boolean).join(" · ")}</div>}
        </li>
      ))}
    </ul>
  );
}

export default function Vendors() {
  return (<><PageTitle title="Vendors" sub="Planners, venues and partners" /><Suspense fallback={<Skeleton rows={6} />}><List /></Suspense></>);
}
