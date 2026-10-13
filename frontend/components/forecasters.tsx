import { pct } from "@/lib/format";
import { FRAMING, KIND_HEADING } from "@/lib/labels";
import type { Run } from "@/lib/types";

/** The estimates side by side (three forecasters, the median, the plain AI call), then each forecaster's reasoning. */
export function ForecastersSection({ run }: { run: Run }) {
  const outcomes = run.prediction?.outcomes;
  if (!outcomes || run.forecasts.length === 0) return null;

  const byForecaster = new Map<number, { variant: string; reasoning: string; probs: Map<string, number> }>();
  for (const f of run.forecasts) {
    const entry = byForecaster.get(f.forecaster_index) ?? { variant: f.variant, reasoning: f.reasoning, probs: new Map() };
    entry.probs.set(f.market_ticker, f.probability);
    byForecaster.set(f.forecaster_index, entry);
  }
  const forecasters = [...byForecaster.entries()].sort((a, b) => a[0] - b[0]);
  const columns: { name: string; strong?: boolean; value: (ticker: string) => number | null }[] = [
    ...forecasters.map(([index, f]) => ({
      name: `Forecaster ${index + 1}`,
      value: (t: string) => f.probs.get(t) ?? null,
    })),
    { name: "Our probability (the middle one)", strong: true, value: (t) => outcomes.find((o) => o.market_ticker === t)?.probability ?? null },
    ...(run.baseline ? [{ name: "Plain AI call, no research", value: (t: string) => run.baseline?.[t] ?? null }] : []),
  ];
  const kinds = [...new Set(outcomes.map((o) => o.kind ?? "winner"))];

  return (
    <section className="mb-8" aria-labelledby="forecasters-heading">
      <h2 id="forecasters-heading" className="mb-1 text-xl font-semibold tracking-tight">
        The forecasts
      </h2>
      <p className="mb-3 text-sm text-muted-foreground">
        Each forecaster saw only the checked facts. The plain AI call saw no facts at all, so the difference shows what the research added.
      </p>
      <div className="overflow-x-auto rounded-xl border bg-card">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b">
              <th className="px-4 py-3 font-medium">Outcome</th>
              {columns.map((c) => (
                <th key={c.name} className={`px-4 py-3 font-medium ${c.strong ? "bg-ours-soft" : ""}`}>
                  {c.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {kinds.map((kind) => [
              kinds.length > 1 ? (
                <tr key={`h-${kind}`} className="border-b bg-muted">
                  <td colSpan={columns.length + 1} className="px-4 py-2 font-medium">
                    {KIND_HEADING[kind] ?? kind}
                  </td>
                </tr>
              ) : null,
              ...outcomes
                .filter((o) => (o.kind ?? "winner") === kind)
                .map((o) => (
                  <tr key={o.market_ticker} className="border-b last:border-b-0">
                    <td className="px-4 py-2.5">{o.outcome}</td>
                    {columns.map((c) => {
                      const v = c.value(o.market_ticker);
                      return (
                        <td key={c.name} className={`px-4 py-2.5 tabular-nums ${c.strong ? "bg-ours-soft font-semibold" : ""}`}>
                          {v === null ? "–" : pct(v)}
                        </td>
                      );
                    })}
                  </tr>
                )),
            ])}
          </tbody>
        </table>
      </div>
      <div className="mt-3 grid gap-2">
        {forecasters.map(([index, f]) => (
          <details key={index} className="rounded-xl border bg-card px-4 py-3">
            <summary className="cursor-pointer font-medium">
              Forecaster {index + 1}: {FRAMING[f.variant] ?? f.variant}
            </summary>
            <p className="mt-2 whitespace-pre-line text-sm text-muted-foreground">{f.reasoning}</p>
          </details>
        ))}
      </div>
    </section>
  );
}
