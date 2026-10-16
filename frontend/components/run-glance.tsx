import { duration, gapCents, money } from "@/lib/format";
import { isMarketFinding, plainReason, sideText } from "@/lib/labels";
import type { Run } from "@/lib/types";

/** The top of a finished run's page: what matters, before the detail. Computed from the run itself. */
export function RunGlance({ run }: { run: Run }) {
  const p = run.prediction;
  const comparison = p?.comparison?.outcomes ?? [];
  const labels = new Map((p?.outcomes ?? []).map((o) => [o.market_ticker, o.outcome]));
  const flagged = comparison.filter((o) => o.meaningful).sort((a, b) => (b.net_edge ?? 0) - (a.net_edge ?? 0));
  const findings = (run.result?.findings ?? []).filter((f) => !isMarketFinding(f));
  const cited = findings.reduce((n, f) => n + f.claims.filter((c) => c.kind === "sourced").length, 0);

  let reason: string | null = null;
  if (p?.outcomes && comparison.length > 0 && flagged.length === 0) {
    const counts = new Map<string, number>();
    for (const o of comparison) for (const r of o.reasons.map(plainReason)) counts.set(r, (counts.get(r) ?? 0) + 1);
    const top = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
    reason = top ? `${top[0]} (${top[1]} of ${comparison.length} markets)` : null;
  }

  return (
    <section className="mb-6 rounded-xl border bg-card p-5" aria-labelledby="glance-heading">
      <h2 id="glance-heading" className="mb-3 text-lg font-semibold tracking-tight">
        At a glance
      </h2>
      {!p?.outcomes ? (
        <p className="text-muted-foreground">{p?.unavailable ?? "There is no forecast for this run."} The research below is still available.</p>
      ) : flagged.length === 0 ? (
        <p>
          <span className="font-semibold">No market is worth a look.</span>
          {reason ? <span className="text-muted-foreground"> Most common reason: {reason}.</span> : null}
        </p>
      ) : (
        <div>
          <p className="font-semibold">
            {flagged.length} market{flagged.length === 1 ? " is" : "s are"} worth a look.
          </p>
          <ul className="mt-1 grid gap-0.5">
            {flagged.slice(0, 5).map((o) => (
              <li key={o.market_ticker}>
                <span className="font-medium">{labels.get(o.market_ticker) ?? o.market_ticker}</span>: {sideText(o)}, gap{" "}
                <span className="font-semibold text-good">{gapCents(o.net_edge ?? 0)}</span> after fees
              </li>
            ))}
            {flagged.length > 5 ? <li className="text-muted-foreground">and {flagged.length - 5} more, in the table below.</li> : null}
          </ul>
        </div>
      )}
      <dl className="mt-4 grid gap-x-8 gap-y-1 text-sm sm:grid-cols-2 lg:grid-cols-4">
        {[
          ["Facts supported by their page", p?.supported_claims === undefined ? "–" : `${p.supported_claims} of ${cited} cited`],
          ["Valid forecasters", p?.forecasters_valid === undefined ? "–" : String(p.forecasters_valid)],
          ["Time taken", duration(run.started_at, run.finished_at)],
          ["Cost", money(run.cost_usd)],
        ].map(([label, value]) => (
          <div key={label} className="flex justify-between gap-3 sm:block">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="font-medium tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-sm text-muted-foreground">“Worth a look” is not a recommendation. Prices are for the moment they were read.</p>
    </section>
  );
}
