import Link from "next/link";
import { Suspense } from "react";
import { loadHandled } from "@/lib/data";
import { Empty } from "@/components/ui";
import { PageTitle, Skeleton } from "@/components/page-title";
import { Reopen } from "./reopen";

async function List() {
  const { alerts, error } = await loadHandled();
  if (error) return <Empty>Couldn&apos;t load: {error}</Empty>;
  if (!alerts.length) return <Empty>Nothing handled yet.</Empty>;
  return (
    <ul className="card mt-4 divide-y divide-[var(--line)]">
      {alerts.map((a) => (
        <li key={a.id} className="flex items-center gap-3 px-4 py-3">
          <div className="min-w-0 flex-1">
            <div className="truncate font-medium">{a.title}</div>
            <div className="truncate text-[13px] text-[var(--muted)]">{a.at ? new Date(a.at).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "America/Chicago" }) : ""} · {a.detail.split("\n")[0].slice(0, 80)}</div>
          </div>
          <Reopen id={a.id} />
        </li>
      ))}
    </ul>
  );
}

export default function Handled() {
  return (
    <>
      <div className="pt-3"><Link href="/inbox" className="text-sm font-medium text-[var(--accent)]">‹ Inbox</Link></div>
      <PageTitle title="Handled" sub="The last 30 · reopen anything marked by mistake" />
      <Suspense fallback={<Skeleton />}><List /></Suspense>
    </>
  );
}
