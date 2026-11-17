export function PageTitle({ title, sub, right }: { title: string; sub?: React.ReactNode; right?: React.ReactNode }) {
  return (
    <header className="flex items-end justify-between gap-3 pb-1 pt-3">
      <div>
        <h1 className="font-serif text-[28px] font-semibold leading-tight tracking-tight">{title}</h1>
        {sub && <p className="mt-0.5 text-sm text-[var(--muted)]">{sub}</p>}
      </div>
      {right}
    </header>
  );
}

export function Skeleton({ rows = 4 }: { rows?: number }) {
  return <div className="mt-4 space-y-3">{Array.from({ length: rows }, (_, i) => <div key={i} className="card h-20 animate-pulse" />)}</div>;
}
