import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Fold } from "@/components/fold";
import { PrepareOrder } from "@/components/prepare-order";
import { AddToTicket } from "@/components/ticket";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ago, cents, gapCents, pct } from "@/lib/format";
import { KIND_HEADING, plainReason, sideText } from "@/lib/labels";
import type { ComparisonOutcome, PredictionOutcome, Run } from "@/lib/types";

type Row = { outcome: PredictionOutcome; market: ComparisonOutcome | null };

function TicketButtons({ outcome, market, run }: { outcome: PredictionOutcome; market: ComparisonOutcome; run: { id: string; event_ticker: string; event_title: string } }) {
  const sides = [
    { side: "yes" as const, price: market.yes_ask, probability: outcome.probability },
    { side: "no" as const, price: market.no_ask, probability: 1 - outcome.probability },
  ];
  return (
    <div className="flex flex-wrap gap-2">
      {sides.map((s) =>
        s.price === null ? null : (
          <AddToTicket
            key={s.side}
            leg={{ runId: run.id, eventTicker: run.event_ticker, marketTicker: market.market_ticker, title: run.event_title, market: outcome.outcome, side: s.side, price: s.price, probability: s.probability, flagged: market.meaningful && market.side === s.side }}
          />
        ),
      )}
    </div>
  );
}

function FlagCell({ outcome, market, run }: { outcome: PredictionOutcome; market: ComparisonOutcome | null; run: { id: string; event_ticker: string; event_title: string } }) {
  if (!market) return <span className="text-muted-foreground">No market price</span>;
  const reasons = market.reasons.map(plainReason);
  return (
    <div className="grid gap-2">
      {market.meaningful ? (
        <>
          <Badge className="bg-good-soft text-good">Worth a look</Badge>
          <PrepareOrder runId={run.id} marketTicker={market.market_ticker} />
        </>
      ) : (
        <span className="text-sm text-muted-foreground">
          Not flagged{reasons.length > 0 ? `: ${reasons.join("; ")}` : ""}
        </span>
      )}
      <TicketButtons outcome={outcome} market={market} run={run} />
    </div>
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

function Change({ now, before }: { now: number; before: number | undefined }) {
  if (before === undefined) return null;
  const d = Math.round((now - before) * 100);
  return (
    <div className="text-sm font-normal text-muted-foreground" title="The forecast of the run this one updates">
      was {pct(before)} ({d > 0 ? "+" : d < 0 ? "−" : ""}{Math.abs(d)} points)
    </div>
  );
}

function GroupRows({ rows, run, previous }: { rows: Row[]; run: { id: string; event_ticker: string; event_title: string }; previous?: Record<string, number> | null }) {
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
              <TableCell className="px-4 py-3.5 text-lg font-semibold tabular-nums">
                {pct(outcome.probability)}
                <Change now={outcome.probability} before={previous?.[outcome.market_ticker]} />
              </TableCell>
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
                <FlagCell outcome={outcome} market={market} run={run} />
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
            <span className="text-lg font-semibold tabular-nums">
              {pct(outcome.probability)}
              <Change now={outcome.probability} before={previous?.[outcome.market_ticker]} />
            </span>
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
            <FlagCell outcome={outcome} market={market} run={run} />
          </div>
        </li>
      ))}
    </ul>

    </>
  );
}

function BookmakersFold({ run, rows }: { run: Run; rows: Row[] }) {
  const withBook = rows.filter((r) => r.outcome.kind === undefined || r.outcome.kind === "winner").filter((r) => r.market?.book);
  if (withBook.length === 0) {
    return run.book_note ? <p className="mt-3 text-sm text-muted-foreground">No bookmaker price for this game: {run.book_note}.</p> : null;
  }
  return (
    <div className="mt-4">
      <Fold
        id="bookmakers"
        level="h3"
        defaultOpen
        title="Bookmakers"
        summary={`${withBook[0].market?.book?.count} bookmakers, their margin removed; the gap is against the Kalshi price after fees`}
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Outcome</TableHead>
              <TableHead className="text-right">Ours</TableHead>
              <TableHead className="text-right">Bookmakers</TableHead>
              <TableHead className="text-right">Pinnacle</TableHead>
              <TableHead>Gap against them, after fees</TableHead>
              <TableHead>Contracts</TableHead>
              <TableHead>Compared with us</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {withBook.map(({ outcome, market }) => {
              const b = market!.book!;
              const price = b.side === "yes" ? market!.yes_ask : b.side === "no" ? market!.no_ask : null;
              return (
                <TableRow key={outcome.market_ticker}>
                  <TableCell className="whitespace-normal font-medium">{outcome.outcome}</TableCell>
                  <TableCell className="text-right tabular-nums">{pct(outcome.probability)}</TableCell>
                  <TableCell className="text-right tabular-nums">{pct(b.probability)}</TableCell>
                  <TableCell className="text-right tabular-nums">{b.pinnacle === null ? "–" : pct(b.pinnacle)}</TableCell>
                  <TableCell className="whitespace-normal tabular-nums">
                    {b.edge === null || b.side === null ? "–" : (
                      <>
                        <span className={b.passes ? "font-semibold text-good" : "font-medium"}>{gapCents(b.edge)}</span>
                        <span className="block text-sm text-muted-foreground">buying “{b.side}” at {cents(price)}</span>
                      </>
                    )}
                  </TableCell>
                  <TableCell className="whitespace-normal text-sm">{b.edge !== null && b.edge > 0 ? (b.enough_contracts ? "enough on offer" : "too few on offer") : "–"}</TableCell>
                  <TableCell className="whitespace-normal text-sm">
                    {b.agrees_with_us === null ? "No gap against the bookmakers" : b.agrees_with_us ? "They agree with us" : "They disagree with us"}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        <p className="mt-3 text-sm text-muted-foreground">
          Read {ago(withBook[0].market?.book?.read_at ?? null)}. This is shown beside our forecast and does not change the flag. A gap passes (green) when it is at least the minimum gap and enough contracts are offered.
        </p>
      </Fold>
    </div>
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

      {groups.map(([kind, groupRows], i) => {
        const flagged = groupRows.filter((r) => r.market?.meaningful).length;
        return groups.length > 1 ? (
          <Fold
            key={kind}
            level="h3"
            title={KIND_HEADING[kind] ?? kind}
            defaultOpen={i === 0}
            summary={`${groupRows.length} market${groupRows.length === 1 ? "" : "s"}${flagged > 0 ? `, ${flagged} worth a look` : ""}`}
          >
            <GroupRows rows={groupRows} run={run} previous={run.previous?.probabilities} />
          </Fold>
        ) : (
          <div key={kind} className="mb-5">
            <GroupRows rows={groupRows} run={run} previous={run.previous?.probabilities} />
          </div>
        );
      })}

      <BookmakersFold run={run} rows={rows} />

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
      </div>
      <div className="mt-4">
        <Fold title="How a market gets the flag" summary="The tests behind “Worth a look”" level="h3">
          <p className="text-sm text-muted-foreground">
            A market is marked “Worth a look” only when the gap after fees is large enough but not suspiciously large, the research moved our probability
          away from what the same AI says with no facts (toward the gap), the forecasters agree, enough claims were supported, and enough contracts are on offer.
          “Worth a look” is not a recommendation. The limits that decide it are placeholders until we have scored real forecasts, and the fee
          formula is taken from public descriptions of Kalshi’s fees.
          </p>
        </Fold>
      </div>
    </section>
  );
}
