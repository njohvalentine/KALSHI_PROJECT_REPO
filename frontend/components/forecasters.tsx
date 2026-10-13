import { pct } from "@/lib/format";
import { FRAMING } from "@/lib/labels";
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
  const lines: { name: string; strong?: boolean; value: (ticker: string) => number | null }[] = [
    ...forecasters.map(([index, f]) => ({
      name: `Forecaster ${index + 1}: ${FRAMING[f.variant] ?? f.variant}`,
      value: (t: string) => f.probs.get(t) ?? null,
    })),
    { name: "Our probability (the middle one)", strong: true, value: (t) => outcomes.find((o) => o.market_ticker === t)?.probability ?? null },
    ...(run.baseline ? [{ name: "Plain AI call, no research", value: (t: string) => run.baseline?.[t] ?? null }] : []),
  ];

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
              <th className="px-4 py-3 font-medium">Estimate</th>
              {outcomes.map((o) => (
                <th key={o.market_ticker} className="px-4 py-3 font-medium">
                  {o.outcome}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {lines.map((l) => (
              <tr key={l.name} className={`border-b last:border-b-0 ${l.strong ? "bg-ours-soft font-semibold" : ""}`}>
                <td className="px-4 py-2.5">{l.name}</td>
                {outcomes.map((o) => {
                  const v = l.value(o.market_ticker);
                  return (
                    <td key={o.market_ticker} className="px-4 py-2.5 tabular-nums">
                      {v === null ? "–" : pct(v)}
                    </td>
                  );
                })}
              </tr>
            ))}
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
