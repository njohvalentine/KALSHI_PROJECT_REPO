import Link from "next/link";
import { Suspense } from "react";
import { AnalyzeButton } from "@/components/analyze-button";
import { LocalTime } from "@/components/local-time";
import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { backendFetch } from "@/lib/backend";
import { ago, bidAsk, pct, RUN_COST_NOTE } from "@/lib/format";
import type { GamesResponse, LatestForecast, LatestRun, RunSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

type Params = { sport?: string; q?: string; started?: string; more?: string };

function href(params: Params, change: Partial<Params>): string {
  const merged = { ...params, ...change };
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(merged)) if (value) query.set(key, value);
  const text = query.toString();
  return text ? `/games?${text}` : "/games";
}

async function GamesList({ params }: { params: Params }) {
  const query = new URLSearchParams({ limit: "200" });
  if (params.sport) query.set("sport", params.sport);
  if (params.q) query.set("q", params.q);
  if (params.started) query.set("include_started", "true");
  if (params.more && params.sport) query.set("more", "true"); // also load the sport's other leagues found on Kalshi (slower)
  // Both lookups run together. The latest-run lookup only decorates the buttons; if it fails the
  // list still works and the buttons simply start fresh.
  const [res, latestRes] = await Promise.all([backendFetch(`/api/games?${query}`), backendFetch("/api/runs/latest")]);

  if (!res.ok) {
    const detail = await res.json().then((b) => b.detail as string, () => "");
    return (
      <Alert variant="destructive">
        <AlertTitle>Games could not be loaded</AlertTitle>
        <AlertDescription>{detail || `The server answered with HTTP ${res.status}.`} Reload the page to try again.</AlertDescription>
      </Alert>
    );
  }
  const data = (await res.json()) as GamesResponse;
  const latest = new Map<string, { id: string; status: RunSummary["status"] }>();
  const forecasts = new Map<string, LatestForecast>();
  if (latestRes.ok) {
    for (const r of ((await latestRes.json()) as { runs: LatestRun[] }).runs) {
      latest.set(r.event_ticker, { id: r.id, status: r.status });
      if (r.forecast) forecasts.set(r.event_ticker, r.forecast);
    }
  }

  return (
    <>
      <nav aria-label="Sport" className="mb-4 flex flex-wrap gap-2">
        {[{ label: "All", value: undefined }, ...data.sports.map((s) => ({ label: s, value: s }))].map((s) => {
          const active = (params.sport ?? undefined) === s.value || (!params.sport && !s.value);
          return (
            <Link
              key={s.label}
              href={href(params, { sport: s.value })}
              aria-current={active ? "page" : undefined}
              className={cn(buttonVariants({ variant: active ? "default" : "outline", size: "sm" }))}
            >
              {s.label}
            </Link>
          );
        })}
      </nav>

      {data.more_sports.length > 0 ? (
        <div className="mb-4">
          <p className="mb-2 text-sm text-muted-foreground">
            More on Kalshi, found by the app. They load slower, and until a sport has {data.measured_min_games} scored games its forecasts are not yet measured.
          </p>
          <nav aria-label="More sports on Kalshi" className="flex flex-wrap gap-2">
            {data.more_sports.map((m) => {
              const active = params.sport === m.sport && Boolean(params.more);
              return (
                <Link
                  key={m.sport}
                  href={href(params, { sport: m.sport, more: "1" })}
                  aria-current={active ? "page" : undefined}
                  className={cn(buttonVariants({ variant: active ? "default" : "outline", size: "sm" }))}
                >
                  {m.sport}
                  {m.also_measured ? " (other leagues)" : ""} · {m.games}
                </Link>
              );
            })}
          </nav>
        </div>
      ) : null}

      {data.errors.length > 0 ? (
        <Alert className="mb-4">
          <AlertTitle>Some leagues could not be loaded</AlertTitle>
          <AlertDescription>
            {data.errors.map((e) => e.league).join(", ")}. The games below are from the other leagues. Reload to try again.
          </AlertDescription>
        </Alert>
      ) : null}

      {data.notes.length > 0 ? (
        <Alert className="mb-4">
          <AlertTitle>Please note</AlertTitle>
          <AlertDescription>{data.notes.join(" ")}</AlertDescription>
        </Alert>
      ) : null}

      {data.games.length === 0 ? (
        <p className="text-muted-foreground">
          {params.q || params.sport ? "No upcoming games match." : "No upcoming games were found."}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="px-4 py-3">Game</TableHead>
                <TableHead className="hidden px-4 py-3 md:table-cell">Starts</TableHead>
                <TableHead className="px-4 py-3">Outcomes (sell – buy price)</TableHead>
                <TableHead className="hidden px-4 py-3 text-right md:table-cell">Research (costs credit)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.games.map((g) => (
                <TableRow key={g.event_ticker}>
                  <TableCell className="whitespace-normal px-4 py-3.5">
                    <span className="block max-w-[34ch] font-medium">{g.title}</span>
                    <span className="block text-sm text-muted-foreground">
                      {g.league}
                      {!g.measured ? (
                        <Badge variant="outline" className="ml-2" title={`${g.scored_games} scored games in ${g.sport} so far; ${data.measured_min_games} are needed`}>
                          Not yet measured
                        </Badge>
                      ) : null}
                    </span>
                    <span className="mt-1 block text-sm md:hidden">
                      <LocalTime iso={g.starts_at} />
                      {g.started ? <Badge className="ml-2 bg-warn-soft text-warn">Started</Badge> : null}
                    </span>
                  </TableCell>
                  <TableCell className="hidden whitespace-normal px-4 py-3.5 md:table-cell">
                    <LocalTime iso={g.starts_at} />
                    {g.started ? <Badge className="ml-2 bg-warn-soft text-warn">Started</Badge> : null}
                  </TableCell>
                  <TableCell className="whitespace-normal px-4 py-3.5">
                    <ul className="grid gap-0.5">
                      {g.outcomes.map((o) => {
                        const ours = forecasts.get(g.event_ticker)?.outcomes.find((x) => x.market_ticker === o.market_ticker);
                        return (
                          <li key={o.market_ticker} className="flex flex-wrap justify-between gap-x-6 text-sm">
                            <span>{o.label}</span>
                            <span className="tabular-nums text-muted-foreground">
                              {ours ? (
                                <span className="mr-3 font-medium text-foreground">
                                  Our estimate {pct(ours.probability)}
                                  {ours.flagged ? <Badge className="ml-1.5 bg-good-soft text-good">Worth a look</Badge> : null}
                                </span>
                              ) : null}
                              {bidAsk(o.bid, o.ask)}
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                    {forecasts.get(g.event_ticker) ? (
                      <p className="mt-1 text-xs text-muted-foreground">
                        Estimate made {ago(forecasts.get(g.event_ticker)?.forecast_at ?? null)}; the prices are live.
                      </p>
                    ) : null}
                    <div className="mt-2 md:hidden">
                      <AnalyzeButton eventTicker={g.event_ticker} latest={latest.get(g.event_ticker) ?? null} />
                    </div>
                  </TableCell>
                  <TableCell className="hidden px-4 py-3.5 text-right md:table-cell">
                    <AnalyzeButton eventTicker={g.event_ticker} latest={latest.get(g.event_ticker) ?? null} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <p className="mt-3 text-sm text-muted-foreground">
        {data.total > data.games.length ? `Showing the first ${data.games.length} of ${data.total} games. ` : ""}
        {data.hidden_started > 0 ? (
          <>
            {data.hidden_started} game(s) that already started are hidden.{" "}
            <Link href={href(params, { started: "1" })} className="text-primary underline underline-offset-4">
              Show started games
            </Link>
          </>
        ) : params.started ? (
          <Link href={href(params, { started: undefined })} className="text-primary underline underline-offset-4">
            Hide started games
          </Link>
        ) : null}
        {" "}Each pair is the price you could sell at and the price you could buy at on Kalshi, in cents. The list can be up to a minute old.
      </p>
    </>
  );
}

function GamesLoading() {
  return (
    <div role="status" aria-live="polite">
      <p className="mb-3 text-muted-foreground">Loading games from Kalshi…</p>
      <div className="overflow-hidden rounded-xl border bg-card">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="flex gap-6 border-b px-4 py-5 last:border-b-0">
            <div className="h-4 flex-1 rounded bg-muted motion-safe:animate-pulse" />
            <div className="h-4 w-24 rounded bg-muted motion-safe:animate-pulse" />
            <div className="h-4 w-40 rounded bg-muted motion-safe:animate-pulse" />
          </div>
        ))}
      </div>
    </div>
  );
}

export default async function GamesPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const raw = await searchParams;
  const first = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) || undefined;
  const params: Params = { sport: first(raw.sport), q: first(raw.q), started: first(raw.started), more: first(raw.more) };
  return (
    <>
      <PageHeader
        title="Games"
        description={`Upcoming games on Kalshi, soonest first. Press Research to look into a game and get our estimate for each outcome. An estimate is for the moment it was made; prices move. ${RUN_COST_NOTE}`}
      />
      <form action="/games" method="get" className="mb-4 flex max-w-md gap-2">
        {params.sport ? <input type="hidden" name="sport" value={params.sport} /> : null}
        {params.started ? <input type="hidden" name="started" value={params.started} /> : null}
        {params.more ? <input type="hidden" name="more" value={params.more} /> : null}
        <Input name="q" defaultValue={params.q ?? ""} placeholder="Search by team, player or league" className="bg-card" aria-label="Search games" />
        <button type="submit" className={buttonVariants({ variant: "outline" })}>
          Search
        </button>
      </form>
      <Suspense key={`${params.sport}|${params.q}|${params.started}|${params.more}`} fallback={<GamesLoading />}>
        <GamesList params={params} />
      </Suspense>
    </>
  );
}
