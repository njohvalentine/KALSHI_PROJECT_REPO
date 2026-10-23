import Link from "next/link";
import { Confidence } from "@/components/confidence";
import { LocalTime } from "@/components/local-time";
import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { backendFetch } from "@/lib/backend";
import { cents, gapCents, pct } from "@/lib/format";
import { plainReason } from "@/lib/labels";
import type { RankedOutcome, RankingResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

type Search = { sort?: string; all?: string; sport?: string; kind?: string };

const score = (x: number | null) => (x === null ? "–" : x.toFixed(3));

function href(current: Search, change: Partial<Search>): string {
  const next = { ...current, ...change };
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(next)) if (v) q.set(k, v);
  const text = q.toString();
  return text ? `/ranking?${text}` : "/ranking";
}

function Choice({ to, active, children }: { to: string; active: boolean; children: React.ReactNode }) {
  return (
    <Link href={to} aria-current={active ? "true" : undefined} className={cn("rounded-lg px-2.5 py-1.5 text-sm font-medium", active ? "bg-secondary text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground")}>
      {children}
    </Link>
  );
}

function evidenceLine(o: RankedOutcome): string {
  const t = o.source_tiers;
  const facts = `${o.supported_claims} supported fact${o.supported_claims === 1 ? "" : "s"}`;
  return t ? `${facts}: ${t.official} official, ${t.news} news, ${t.other} other` : facts;
}

function Row({ o }: { o: RankedOutcome }) {
  const stale = o.confidence.reasons.some((r) => r.includes("older than"));
  return (
    <TableRow className={cn("align-top", stale && "opacity-70")}>
      <TableCell className="min-w-32 whitespace-normal">
        <Link href={`/prediction/${o.run_id}`} className="font-semibold text-primary underline-offset-4 hover:underline">
          {o.title}
        </Link>
        <div className="text-sm text-muted-foreground">
          starts <LocalTime iso={o.starts_at} />
        </div>
        {o.sport ? <div className="text-sm text-muted-foreground">{o.league ?? o.sport}</div> : null}
      </TableCell>
      <TableCell className="min-w-40 whitespace-normal">
        <div className="font-medium">{o.market}</div>
        <div className="text-sm text-muted-foreground">{o.kind === "winner" ? "match result" : `our pick: “${o.side}”`}</div>
        {o.flagged ? <Badge className="mt-1 bg-good-soft text-good">Worth a look</Badge> : null}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        <div className="text-lg font-semibold">{pct(o.our_probability)}</div>
        <div className="text-sm text-muted-foreground">
          range {pct(o.range.low)} to {pct(o.range.high)}
        </div>
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {cents(o.price)}
        <div className="text-sm text-muted-foreground">Kalshi price</div>
        {o.bookmaker_probability !== null ? (
          <div className="text-sm text-muted-foreground">bookmakers {pct(o.bookmaker_probability)}</div>
        ) : null}
      </TableCell>
      <TableCell className={cn("text-right text-lg tabular-nums", o.flagged ? "font-bold text-good" : "font-semibold")}>{gapCents(o.gap)}</TableCell>
      <TableCell className="min-w-44 max-w-64 whitespace-normal">
        <Confidence level={o.confidence.level} reasons={o.confidence.reasons} />
        <div className="mt-1 text-sm">{evidenceLine(o)}</div>
      </TableCell>
      <TableCell className="min-w-28 max-w-56 whitespace-normal text-sm text-muted-foreground">
        {o.risks.length ? (
          <details>
            <summary className="cursor-pointer text-primary">
              {o.risks.length} risk{o.risks.length === 1 ? "" : "s"}
            </summary>
            <ul className="mt-1 list-disc pl-4">
              {o.risks.map((r) => (
                <li key={r}>{plainReason(r)}</li>
              ))}
            </ul>
          </details>
        ) : (
          "none noted"
        )}
      </TableCell>
    </TableRow>
  );
}

export default async function RankingPage({ searchParams }: { searchParams: Promise<Search> }) {
  const search = await searchParams;
  const sort = search.sort === "gap" ? "gap" : "probability";
  const q = new URLSearchParams({ sort, hide_at: search.all ? "1" : "0.90" });
  if (search.sport) q.set("sport", search.sport);
  if (search.kind) q.set("kind", search.kind);
  const res = await backendFetch(`/api/ranking?${q}`);
  if (!res.ok) {
    return (
      <>
        <PageHeader title="Ranking" />
        <Alert variant="destructive">
          <AlertTitle>The ranking could not be loaded</AlertTitle>
          <AlertDescription>The server answered with HTTP {res.status}. Reload the page to try again.</AlertDescription>
        </Alert>
      </>
    );
  }
  const d = (await res.json()) as RankingResponse;
  const cur: Search = { sort: sort === "gap" ? "gap" : undefined, all: search.all, sport: search.sport, kind: search.kind };
  const lc = d.label_check;
  return (
    <>
      <PageHeader title="Ranking" description="Every market of the researched games that have not started, with the Kalshi price and the gap beside it. A match result shows the outcome itself; any other market shows the side Our Agent thinks more likely." />
      <Alert className="mb-4">
        <AlertTitle>How to read this</AlertTitle>
        <AlertDescription>
          <p>
            “Most probable” is not the same as “good value”: the likeliest outcomes are usually the big favourites, and a favourite priced the same as its chance has no gap. Look at both numbers. The gap is our probability minus
            the Kalshi price minus the fee, for the side shown.
          </p>
          <p className="mt-2">
            The confidence level says how consistent our three forecasts and the evidence are. It is not a chance of being right.
            {d.accuracy.games > 0 ? (
              <>
                {" "}
                On {d.accuracy.games} finished games, Kalshi’s price scored {score(d.accuracy.kalshi)} and our forecasts {score(d.accuracy.ours)} (a Brier score; lower is better).
              </>
            ) : null}{" "}
            Our forecasts inside each level, on all scored outcomes, with Kalshi’s price on the same outcomes: rated low {score(lc.low.ours)} against {score(lc.low.kalshi)} ({lc.low.n} outcomes); not rated low{" "}
            {score(lc.medium_or_high.ours)} against {score(lc.medium_or_high.kalshi)} ({lc.medium_or_high.n}). Older records have no source kinds, so none of them can count as high.
          </p>
        </AlertDescription>
      </Alert>
      <div className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-2">
        <div className="flex flex-wrap items-center gap-1">
          <span className="mr-1 text-sm text-muted-foreground">Order:</span>
          <Choice to={href(cur, { sort: undefined })} active={sort === "probability"}>Most probable</Choice>
          <Choice to={href(cur, { sort: "gap" })} active={sort === "gap"}>Biggest gap</Choice>
        </div>
        <div className="flex flex-wrap items-center gap-1">
          <span className="mr-1 text-sm text-muted-foreground">Priced at 90¢ or more:</span>
          <Choice to={href(cur, { all: undefined })} active={!search.all}>Hidden</Choice>
          <Choice to={href(cur, { all: "1" })} active={!!search.all}>Shown</Choice>
        </div>
        {d.sports.length > 1 ? (
          <div className="flex flex-wrap items-center gap-1">
            <span className="mr-1 text-sm text-muted-foreground">Sport:</span>
            <Choice to={href(cur, { sport: undefined })} active={!search.sport}>All</Choice>
            {d.sports.map((s) => (
              <Choice key={s} to={href(cur, { sport: s })} active={search.sport === s}>{s}</Choice>
            ))}
          </div>
        ) : null}
        {d.kinds.length > 1 ? (
          <div className="flex flex-wrap items-center gap-1">
            <span className="mr-1 text-sm text-muted-foreground">Market:</span>
            <Choice to={href(cur, { kind: undefined })} active={!search.kind}>All</Choice>
            {d.kinds.map((k) => (
              <Choice key={k} to={href(cur, { kind: k })} active={search.kind === k}>{k}</Choice>
            ))}
          </div>
        ) : null}
      </div>
      <p className="mb-2 text-sm text-muted-foreground">
        {d.rows.length} of {d.total_rows} outcomes shown, from {d.games_considered} researched game{d.games_considered === 1 ? "" : "s"} that have not started. Prices are read when the page is opened.
      </p>
      {d.rows.length === 0 ? (
        <p className="text-muted-foreground">Nothing to show. Research a game on the Games page first, or change the filters.</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Game</TableHead>
                <TableHead>Outcome</TableHead>
                <TableHead className="text-right">Our probability</TableHead>
                <TableHead className="text-right">Kalshi</TableHead>
                <TableHead className="text-right">Gap after fees</TableHead>
                <TableHead>Confidence and evidence</TableHead>
                <TableHead>Risks</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {d.rows.map((o) => (
                <Row key={o.market_ticker} o={o} />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </>
  );
}
