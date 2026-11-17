"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/", label: "Today", icon: "M3 11.5 12 4l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" },
  { href: "/inbox", label: "Inbox", icon: "M3 13h5l2 3h4l2-3h5M5 5h14l2 8v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-6z" },
  { href: "/leads", label: "Leads", icon: "M16 19v-1a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v1M9 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6m13 9v-1a4 4 0 0 0-3-3.9M16 4.1a3 3 0 0 1 0 5.8" },
  { href: "/calendar", label: "Calendar", icon: "M7 3v3m10-3v3M4 9h16M5 6h14a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1" },
  { href: "/money", label: "Money", icon: "M12 3v18m4-14H10a3 3 0 0 0 0 6h4a3 3 0 0 1 0 6H7" },
];

export function BottomNav({ inbox }: { inbox: number }) {
  return <NavBar path={usePathname()} inbox={inbox} />;
}

// No hooks: also used as the placeholder while the inbox count loads
export function NavBar({ path, inbox }: { path: string; inbox: number }) {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-20 border-t border-[var(--line)] bg-[var(--panel)]/95 backdrop-blur pb-[env(safe-area-inset-bottom)]">
      <ul className="mx-auto grid max-w-xl grid-cols-5">
        {TABS.map((t) => {
          const on = t.href === "/" ? path === "/" : path.startsWith(t.href);
          return (
            <li key={t.href}>
              <Link href={t.href} className="relative flex flex-col items-center gap-0.5 py-2 text-[11px] font-medium"
                    style={{ color: on ? "var(--accent)" : "var(--muted)" }} aria-current={on ? "page" : undefined}>
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={on ? 2.2 : 1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={t.icon} /></svg>
                {t.label}
                {t.href === "/inbox" && inbox > 0 && (
                  <span className="absolute right-[22%] top-1 min-w-[18px] rounded-full px-1 text-[10px] font-semibold leading-[18px]" style={{ background: "var(--red)", color: "var(--panel)" }}>{inbox}</span>
                )}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
