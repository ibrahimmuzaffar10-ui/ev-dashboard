import { Suspense } from "react";
import { BottomNav, NavBar } from "@/components/nav";
import { loadAlerts } from "@/lib/data";

async function NavWithCount() {
  const { alerts } = await loadAlerts();
  return <BottomNav inbox={alerts.length} />;
}

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <>
      <main className="mx-auto max-w-xl px-4 pb-28 pt-[max(1rem,env(safe-area-inset-top))]">{children}</main>
      <Suspense fallback={<NavBar path="" inbox={0} />}><NavWithCount /></Suspense>
    </>
  );
}
