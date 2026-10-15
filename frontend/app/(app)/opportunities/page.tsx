import Link from "next/link";
import { Suspense } from "react";
import { AnalyzeButton } from "@/components/analyze-button";
import { LocalTime } from "@/components/local-time";
import { AddToTicket } from "@/components/ticket";
import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { backendFetch } from "@/lib/backend";
import { ago, cents, gapCents, pct } from "@/lib/format";
import { plainReason } from "@/lib/labels";
import type { AlertsResponse, OpportunitiesResponse, Opportunity } from "@/lib/types";
import { cn } from "@/lib/utils";

function buyText(o: Opportunity): string {
  const b = o.best;
  if (!b) return "";
  // Only a flagged row reads as something to do; an unflagged one just names the largest gap.
  return o.flagged ? `Buy “${b.side}” on ${b.market} at ${cents(b.price)}` : `Largest gap: buying “${b.side}” on ${b.market} at ${cents(b.price)}`;
}

function Row({ o }: { o: Opportunity }) {
  const b = o.best;
  const risks = [...o.risks.map(plainReason)];
  return (
    <li className={cn("rounded-xl border bg-card p-4", o.stale && "opacity-70")}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div>
          <Link href={`/prediction/${o.run_id}`} className="font-medium text-primary underline-offset-4 hover:underline">
            {o.title}
          </Link>
          <span className="ml-2 text-sm text-muted-foreground">
            starts <LocalTime iso={o.starts_at} />
          </span>
        </div>
        <div className="flex items-center gap-2">
          {o.flagged ? <Badge className="bg-good-soft text-good">Worth a look</Badge> : <Badge variant="outline">Not flagged</Badge>}
          {o.stale ? <Badge className="bg-warn-soft text-warn">Forecast is old</Badge> : null}
        </div>
      </div>

      {o.unavailable || !b ? (
        <p className="mt-2 text-sm text-muted-foreground">{o.unavailable ?? "No price to compare with."}</p>
      ) : (
        <>
          <p className="mt-2 font-medium">{buyText(o)}</p>
          <dl className="mt-2 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div className="flex justify-between gap-3 sm:block">
              <dt className="text-muted-foreground">Our probability / market</dt>
              <dd className="tabular-nums">
                {pct(b.our_probability)} / {pct(b.market_probability)}
              </dd>
            </div>
            <div className="flex justify-between gap-3 sm:block">
              <dt className="text-muted-foreground">Gap now, after fees</dt>
              <dd className="text-lg font-semibold tabular-nums">{gapCents(b.gap)}</dd>
            </div>
            <div className="flex justify-between gap-3 sm:block">
              <dt className="text-muted-foreground">Range of the forecasts</dt>
              <dd className="tabular-nums">{Math.round(b.spread * 100)} points</dd>
            </div>
            <div className="flex justify-between gap-3 sm:block">
              <dt className="text-muted-foreground">Supported claims</dt>
              <dd className="tabular-nums">{o.supported_claims}</dd>
            </div>
          </dl>
          {o.stale ? (
            <p className="mt-2 text-sm text-muted-foreground">The forecast is old: research the game again to add it to a ticket.</p>
          ) : (
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
              <AddToTicket
                leg={{
                  runId: o.run_id, eventTicker: o.event_ticker, marketTicker: b.market_ticker, title: o.title, market: b.market, side: b.side, price: b.price,
                  probability: b.our_probability, flagged: o.flagged,
                }}
              />
              <Link href={`/prediction/${o.run_id}`} className="text-sm text-primary underline underline-offset-4">
                Other markets and the other side: open the game
              </Link>
            </div>
          )}
          {o.flagged && o.flagged_markets > 1 ? (
            <p className="mt-2 text-sm text-muted-foreground">
              {o.flagged_markets - 1} more market{o.flagged_markets - 1 === 1 ? "" : "s"} of this game {o.flagged_markets - 1 === 1 ? "is" : "are"} also worth a look.{" "}
              <Link href={`/prediction/${o.run_id}`} className="text-primary underline underline-offset-4">
                See all
              </Link>
            </p>
          ) : null}
        </>
      )}

      {risks.length > 0 ? <p className="mt-2 text-sm text-muted-foreground">{o.flagged ? "Take care: " : "Why not: "}{risks.join("; ")}.</p> : null}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
        <span>Forecast made {o.age_hours === null ? "at an unknown time" : o.age_hours < 1 ? "less than an hour ago" : `${Math.round(o.age_hours)} h ago`}. Prices are live.</span>
        <AnalyzeButton eventTicker={o.event_ticker} latest={{ id: o.run_id, status: "done" }} />
      </div>
    </li>
  );
}

const ALERT_KIND: Record<string, string> = {
  run_flagged: "Worth a look",
  market_moved: "Market moved",
  no_longer_flagged: "No longer worth a look",
  start_soon: "Starting soon",
};
const ALERT_STATUS: Record<string, string> = { recorded: "Recorded here", sent: "Sent", failed: "Could not be sent", held_back: "Held back" };

async function Alerts() {
  const res = await backendFetch("/api/alerts?limit=10");
  if (!res.ok) return null; // the opportunities above still work without this part
  const { alerts, monitor } = (await res.json()) as AlertsResponse;
  return (
    <section className="mt-8" aria-labelledby="alerts-heading">
      <h2 id="alerts-heading" className="mb-1 text-xl font-semibold tracking-tight">
        Recent alerts
      </h2>
      <p className="mb-3 text-sm text-muted-foreground">
        {monitor.enabled
          ? `The watcher is on (every ${monitor.interval_minutes} minutes${monitor.last_cycle_at ? `, last looked ${ago(monitor.last_cycle_at)}` : ""}). Alerts are ${monitor.channel === "app only" ? "recorded here; no chat channel is connected yet" : "also sent to chat"}.`
          : "The watcher is off, so no alerts are made. It is switched on with MONITOR_ENABLED=true."}
        {monitor.last_error ? ` The last check failed (${monitor.last_error}); see the server log.` : ""}
        {monitor.auto_research_cap > 0
          ? ` Automatic research: ${monitor.auto_research_started_today} of ${monitor.auto_research_cap} games today.`
          : " Automatic research is off."}
      </p>
      {alerts.length === 0 ? (
        <p className="text-sm text-muted-foreground">No alerts yet.</p>
      ) : (
        <ul className="grid gap-2">
          {alerts.map((a) => (
            <li key={a.id} className="rounded-xl border bg-card p-3 text-sm">
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <Badge variant="outline">{ALERT_KIND[a.kind] ?? a.kind}</Badge>
                <Badge className={a.status === "failed" ? "bg-destructive/10 text-destructive" : a.status === "held_back" ? "bg-warn-soft text-warn" : "bg-secondary text-secondary-foreground"}>
                  {ALERT_STATUS[a.status] ?? a.status}
                </Badge>
                <span className="text-muted-foreground">{ago(a.created_at)}</span>
                {a.run_id ? (
                  <Link href={`/prediction/${a.run_id}`} className="text-primary underline underline-offset-4">
                    Open
                  </Link>
                ) : null}
              </div>
              <p>{a.text}</p>
              {a.detail ? <p className="mt-1 text-muted-foreground">Why: {a.detail}</p> : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

async function List({ all }: { all: boolean }) {
  const res = await backendFetch(`/api/opportunities${all ? "?all=true" : ""}`);
  if (!res.ok) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Opportunities could not be loaded</AlertTitle>
        <AlertDescription>The server answered with HTTP {res.status}. Reload the page to try again.</AlertDescription>
      </Alert>
    );
  }
  const data = (await res.json()) as OpportunitiesResponse;
  return (
    <>
      <nav aria-label="Filter" className="mb-4 flex flex-wrap gap-2">
        <Link href="/opportunities" aria-current={!all ? "page" : undefined} className={cn(buttonVariants({ variant: !all ? "default" : "outline", size: "sm" }))}>
          Worth a look only
        </Link>
        <Link href="/opportunities?all=1" aria-current={all ? "page" : undefined} className={cn(buttonVariants({ variant: all ? "default" : "outline", size: "sm" }))}>
          All researched games
        </Link>
      </nav>
      <p className="mb-4 text-sm text-muted-foreground">
        {data.games_considered} researched game{data.games_considered === 1 ? "" : "s"} that have not started; {data.flagged_games} worth a look. Forecasts older than{" "}
        {data.max_age_hours} hours are shown greyed and are not flagged.
      </p>
      {data.opportunities.length === 0 ? (
        <Alert>
          <AlertTitle>{data.games_considered === 0 ? "No researched games yet" : "Nothing is worth a look right now"}</AlertTitle>
          <AlertDescription>
            {data.games_considered === 0 ? (
              <>
                Press Research on a game on the{" "}
                <Link href="/games" className="text-primary underline underline-offset-4">
                  Games
                </Link>{" "}
                page. Games that have already started are not shown.
              </>
            ) : (
              <>
                The most common reasons:
                <ul className="mt-1 list-disc pl-5">
                  {data.top_reasons.map((r) => (
                    <li key={r.reason}>
                      {plainReason(r.reason.replace(/#/g, "0"))} ({r.games} game{r.games === 1 ? "" : "s"})
                    </li>
                  ))}
                </ul>
                <Link href="/opportunities?all=1" className="mt-2 inline-block text-primary underline underline-offset-4">
                  Show all researched games
                </Link>
              </>
            )}
          </AlertDescription>
        </Alert>
      ) : (
        <ul className="grid gap-3">
          {data.opportunities.map((o) => (
            <Row key={o.event_ticker} o={o} />
          ))}
        </ul>
      )}
      <p className="mt-4 text-sm text-muted-foreground">
        “Worth a look” is not a recommendation. The limits behind it are placeholders until we have scored real forecasts, and a gap that looks very large is
        more often the model’s mistake than an opportunity. Nothing here places an order.
      </p>
    </>
  );
}

export default async function OpportunitiesPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const raw = await searchParams;
  const all = Boolean(raw.all);
  return (
    <>
      <PageHeader
        title="Opportunities"
        description="Games we have researched where the market price may be worth a closer look, best gap first, with today’s prices. No new research is run here."
      />
      <Suspense key={String(all)} fallback={<p className="text-muted-foreground" role="status">Reading today’s prices…</p>}>
        <List all={all} />
      </Suspense>
      <Suspense fallback={null}>
        <Alerts />
      </Suspense>
    </>
  );
}
