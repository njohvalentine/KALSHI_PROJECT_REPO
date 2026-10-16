/** A summary card: a small label, one big figure, and a line under it. Used by the Dashboard and the Results page. */
export function Stat({ label, value, sub }: { label: string; value: React.ReactNode; sub: React.ReactNode }) {
  return (
    <div className="rounded-xl border bg-card p-5">
      <div className="text-sm font-medium text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-3xl font-bold tracking-tight">{value}</div>
      <div className="mt-0.5 text-sm text-muted-foreground">{sub}</div>
    </div>
  );
}
