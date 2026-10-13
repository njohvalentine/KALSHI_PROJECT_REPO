import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ago, cents, gapCents, pct } from "@/lib/format";
import { KIND_HEADING, plainReason, sideText } from "@/lib/labels";
import type { ComparisonOutcome, PredictionOutcome, Run } from "@/lib/types";

type Row = { outcome: PredictionOutcome; market: ComparisonOutcome | null };

function FlagCell({ market }: { market: ComparisonOutcome | null }) {
  if (!market) return <span className="text-muted-foreground">No market price</span>;
  if (market.meaningful) return <Badge className="bg-good-soft text-good">Worth a look</Badge>;
  const reasons = market.reasons.map(plainReason);
  return (
    <span className="text-sm text-muted-foreground">
      Not flagged{reasons.length > 0 ? `: ${reasons.join("; ")}` : ""}
    </span>
  );
}

function MarketCell({ market }: { market: ComparisonOutcome | null }) {
  if (!market || (market.yes_ask === null && market.no_ask === null)) return <span className="text-muted-foreground">–</span>;
  return (
    <span className="tabular-nums">
      {cents(market.yes_ask)} <span className="text-sm text-muted-foreground">to buy “yes”</span>
      <br />
      {cents(market.no_ask)} <span className="text-sm text-muted-foreground">to buy “no”</span>
    </span>
  );
}

function GapCell({ market }: { market: ComparisonOutcome | null }) {
  if (!market || market.net_edge === null) return <span className="text-muted-foreground">–</span>;
  return (
    <span className="tabular-nums">
      <span className="font-medium">{gapCents(market.net_edge)}</span>
      <span className="block text-sm text-muted-foreground">{sideText(market)}</span>
    </span>
  );
}

function GroupRows({ rows }: { rows: Row[] }) {
  return (
    <>
      <div className="hidden overflow-x-auto rounded-xl border bg-card sm:block">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="px-4 py-3">Outcome</TableHead>
            <TableHead className="px-4 py-3">Our probability</TableHead>
            <TableHead className="px-4 py-3">Range of the forecasts</TableHead>
            <TableHead className="px-4 py-3">Market price</TableHead>
            <TableHead className="px-4 py-3">Gap after fees</TableHead>
            <TableHead className="px-4 py-3">Flag</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map(({ outcome, market }) => (
            <TableRow key={outcome.market_ticker}>
              <TableCell className="whitespace-normal px-4 py-3.5 font-medium">{outcome.outcome}</TableCell>
              <TableCell className="px-4 py-3.5 text-lg font-semibold tabular-nums">{pct(outcome.probability)}</TableCell>
              <TableCell className="px-4 py-3.5 tabular-nums">
                {pct(outcome.min)}–{pct(outcome.max)}
              </TableCell>
              <TableCell className="px-4 py-3.5">
                <MarketCell market={market} />
              </TableCell>
              <TableCell className="whitespace-normal px-4 py-3.5">
                <GapCell market={market} />
              </TableCell>
              <TableCell className="max-w-[28ch] whitespace-normal px-4 py-3.5">
                <FlagCell market={market} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>

    <ul className="grid gap-3 sm:hidden">
      {rows.map(({ outcome, market }) => (
        <li key={outcome.market_ticker} className="rounded-xl border bg-card p-4">
          <div className="flex items-baseline justify-between gap-3">
            <span className="font-medium">{outcome.outcome}</span>
            <span className="text-lg font-semibold tabular-nums">{pct(outcome.probability)}</span>
          </div>
          <dl className="mt-2 grid gap-1 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Range of the forecasts</dt>
              <dd className="tabular-nums">
                {pct(outcome.min)}–{pct(outcome.max)}
              </dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Market price</dt>
              <dd className="text-right">
                <MarketCell market={market} />
              </dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Gap after fees</dt>
              <dd className="text-right">
                <GapCell market={market} />
              </dd>
            </div>
          </dl>
          <div className="mt-2">
            <FlagCell market={market} />
          </div>
        </li>
      ))}
    </ul>

    </>
  );
}

export function PredictionSection({ run }: { run: Run }) {
  const p = run.prediction;
  if (!p) {
    return run.status === "done" ? (
      <p className="mb-8 text-sm text-muted-foreground">This run was made before forecasts existed, so there is no probability for it.</p>
    ) : null;
  }
  if (p.unavailable || !p.outcomes) {
    return (
      <Alert className="mb-8">
        <AlertTitle>No forecast for this game</AlertTitle>
        <AlertDescription>{p.unavailable ?? "The forecast could not be made."} The research below is still available.</AlertDescription>
      </Alert>
    );
  }
  const markets = new Map((p.comparison?.outcomes ?? []).map((o) => [o.market_ticker, o]));
  const rows: Row[] = p.outcomes.map((o) => ({ outcome: o, market: markets.get(o.market_ticker) ?? null }));
  const comparison = p.comparison;
  const twoWay = rows.filter((r) => (r.outcome.kind ?? "winner") === "winner").length === 2;
  const kinds = [...new Set(rows.map((r) => r.outcome.kind ?? "winner"))];
  const groups: [string, Row[]][] = kinds.map((k) => [k, rows.filter((r) => (r.outcome.kind ?? "winner") === k)]);
  const notOffered = p.markets_not_offered ?? [];
  const adjustments = p.adjustments ?? [];

  return (
    <section className="mb-8" aria-labelledby="prediction-heading">
      <h2 id="prediction-heading" className="mb-1 text-xl font-semibold tracking-tight">
        Our forecast and the market
      </h2>
      <p className="mb-3 text-sm text-muted-foreground">
        Our probability is the middle of {p.forecasters_valid ?? 3} independent forecasts that never saw Kalshi’s price.
        {p.evidence === "none" ? " No claim could be checked against its page, so they worked from general knowledge of the sport." : ""}
      </p>

      {groups.map(([kind, groupRows]) => (
        <div key={kind} className="mb-5">
          {groups.length > 1 ? <h3 className="mb-2 text-lg font-semibold tracking-tight">{KIND_HEADING[kind] ?? kind}</h3> : null}
          <GroupRows rows={groupRows} />
        </div>
      ))}

      <div className="mt-3 grid gap-1 text-sm text-muted-foreground">
        {comparison?.unavailable ? <p>Market prices could not be read for this run: {comparison.unavailable}</p> : null}
        {comparison?.priced_at ? <p>Prices were read {ago(comparison.priced_at)}. They move; the gap is for that moment only.</p> : null}
        {comparison?.fee && comparison.fee.source !== "series" ? (
          <p>The fee could not be read from Kalshi, so a standard fee was assumed ({comparison.fee.source}).</p>
        ) : null}
        {notOffered.length > 0 ? <p>Not offered or not readable for this game: {notOffered.join("; ")}.</p> : null}
        {adjustments.length > 0 ? (
          <p>
            {adjustments.length} small inconsistenc{adjustments.length === 1 ? "y" : "ies"} between related markets in the forecasts (for example a higher line more likely than a
            lower one) {adjustments.length === 1 ? "was" : "were"} fixed by lowering the larger number.
          </p>
        ) : null}
        {twoWay ? <p>In a game with two outcomes, buying “yes” on one side is almost the same bet as buying “no” on the other.</p> : null}
        <p>
          A market is marked “Worth a look” only when the gap after fees is large enough but not suspiciously large, the research moved our probability
          away from what the same AI says with no facts (toward the gap), the forecasters agree, enough claims were supported, and enough contracts are on offer.
          “Worth a look” is not a recommendation. The limits that decide it are placeholders until we have scored real forecasts, and the fee
          formula is taken from public descriptions of Kalshi’s fees.
        </p>
      </div>
    </section>
  );
}
