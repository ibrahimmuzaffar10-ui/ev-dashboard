import Link from "next/link";

// Overview (the money to-do list) · Progress (charts: how the year is going)
export function MoneyTabs({ active }: { active: "overview" | "progress" }) {
  const tab = (href: string, key: string, label: string) => (
    <Link href={href} aria-current={active === key ? "page" : undefined}
          className="flex-1 rounded-lg py-2 text-center text-[14px] font-medium"
          style={active === key ? { background: "var(--panel)", color: "var(--ink)", boxShadow: "var(--shadow)" } : { color: "var(--muted)" }}>
      {label}
    </Link>
  );
  return (
    <nav className="mt-3 flex gap-1 rounded-xl bg-[var(--panel-2)] p-1">
      {tab("/money", "overview", "Overview")}
      {tab("/money/progress", "progress", "Progress")}
    </nav>
  );
}
