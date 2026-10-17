import { Suspense } from "react";
import { PageHeader } from "@/components/page-header";
import { Stat } from "@/components/stat";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { backendFetch } from "@/lib/backend";
import { centsPrecise } from "@/lib/format";
import type { DashboardResponse, OpportunitiesResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

const score = (x: number | null) => (x === null ? "–" : x.toFixed(4));

/** One bar. The longest possible bar is a Brier score of 0.25, what always saying 50% scores. */
function Bar({ label, value, color }: { label: string; value: number | null; color: string }) {
  return (
    <div className="my-2 grid grid-cols-[8rem_1fr_3.5rem] items-center gap-3 text-sm max-sm:grid-cols-[6.5rem_1fr_3.5rem]">
      <span>{label}</span>
      <div className="h-3 overflow-hidden rounded-md bg-muted" role="img" aria-label={`${label}: ${score(value)}`}>
        <div className={cn("h-full rounded-md", color)} style={{ width: `${Math.min(100, ((value ?? 0) / 0.25) * 100)}%` }} />
      </div>
      <span className="text-right tabular-nums text-muted-foreground">{value === null ? "–" : value.toFixed(3)}</span>
    </div>
  );
}

async function WorthALook() {
  const res = await backendFetch("/api/opportunities");
  if (!res.ok) return <Stat label="Worth a look today" value="–" sub="Could not be read; open the Opportunities page." />;
  const d = (await res.json()) as OpportunitiesResponse;
  return <Stat label="Worth a look today" value={d.flagged_games} sub={`of ${d.games_considered} researched game${d.games_considered === 1 ? "" : "s"} that have not started`} />;
}

export default async function DashboardPage() {
  const res = await backendFetch("/api/dashboard");
  if (!res.ok) {
    return (
      <>
        <PageHeader title="Dashboard" />
        <Alert variant="destructive">
          <AlertTitle>The Dashboard could not be loaded</AlertTitle>
          <AlertDescription>The server answered with HTTP {res.status}. Reload the page to try again.</AlertDescription>
        </Alert>
      </>
    );
  }
  const d = (await res.json()) as DashboardResponse;
  const f = d.flagged;
  return (
    <>
      <PageHeader title="Dashboard" description="How the system is doing against the Kalshi price, and what is worth a look today." />
      <div className={cn("mb-4 rounded-xl px-4 py-3", d.message.kind === "ahead" ? "bg-good-soft text-good" : "bg-warn-soft text-warn")} role="status">
        {d.message.text}
      </div>
      <div className="mb-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Finished games scored" value={d.games} sub={`${d.outcomes} outcomes${d.unresolved ? ` · ${d.unresolved} more outcomes still to finish` : ""}`} />
        <Suspense fallback={<Stat label="Worth a look today" value="…" sub="Reading today’s prices…" />}>
          <WorthALook />
        </Suspense>
        <Stat
          label="Flagged bets so far"
          value={`${f.won} / ${f.bets}`}
          sub={f.bets === 0 ? "none yet" : `won · paper result ${centsPrecise(f.average_result)} per contract${f.too_few ? " (too few to read)" : ""}`}
        />
        <Stat label="Research spend" value={`$${d.spend.total_usd.toFixed(2)}`} sub={`all time · ${d.spend.runs} runs · estimated${d.spend.limit ? ` · ${d.spend.last_24h} of ${d.spend.limit} games researched in the last 24 hours` : ""}`} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-xl border bg-card p-5" aria-labelledby="all-heading">
          <h2 id="all-heading" className="text-lg font-semibold">Forecast error, all games</h2>
          <p className="mb-3 text-sm text-muted-foreground">Brier score on the same {d.scores.n} outcomes. Lower is better.</p>
          <Bar label="Ours" value={d.scores.ours} color="bg-chart-1" />
          <Bar label="Plain AI" value={d.scores.baseline} color="bg-chart-2" />
          <Bar label="Kalshi price" value={d.scores.market} color="bg-foreground" />
        </section>
        <section className="rounded-xl border bg-card p-5" aria-labelledby="sport-heading">
          <h2 id="sport-heading" className="text-lg font-semibold">By sport</h2>
          <p className="mb-3 text-sm text-muted-foreground">Ours against the Kalshi price. A shorter bar is better.</p>
          {d.by_sport.length === 0 ? (
            <p className="text-sm text-muted-foreground">No finished games yet.</p>
          ) : (
            d.by_sport.map((s) => (
              <div key={s.sport} className="mb-3">
                <Bar label={`${s.sport} · ${s.games}`} value={s.ours} color="bg-chart-1" />
                <Bar label="Kalshi price" value={s.market} color="bg-foreground" />
                {s.too_few ? <p className="text-xs text-muted-foreground">Too few games to read.</p> : null}
              </div>
            ))
          )}
        </section>
      </div>
      {d.bookmakers ? (
        <section className="mt-4 rounded-xl border bg-card p-5" aria-labelledby="book-heading">
          <h2 id="book-heading" className="text-lg font-semibold">Games with bookmaker prices</h2>
          <p className="mb-3 text-sm text-muted-foreground">
            Brier score on the same {d.bookmakers.n} outcomes of {d.bookmakers.games} game{d.bookmakers.games === 1 ? "" : "s"}. Lower is better.
            {d.bookmakers.too_few ? ` Too few games to read: ${d.games_needed} are needed.` : ""}
          </p>
          <Bar label="Ours" value={d.bookmakers.ours} color="bg-chart-1" />
          <Bar label="Kalshi price" value={d.bookmakers.market} color="bg-foreground" />
          <Bar label="Bookmakers" value={d.bookmakers.book} color="bg-chart-3" />
          {d.bookmakers.pinnacle !== null ? <Bar label={`Pinnacle · ${d.bookmakers.pinnacle_n}`} value={d.bookmakers.pinnacle} color="bg-chart-4" /> : null}
        </section>
      ) : null}
      <p className="mt-4 text-sm text-muted-foreground">
        Scores need about {d.games_needed} finished games before they mean anything. Research spend is calculated by the app from the tokens used; it is not the OpenAI bill.
        Nothing here places an order.
      </p>
    </>
  );
}
