import Link from "next/link";
import { LocalTime } from "@/components/local-time";
import { PageHeader } from "@/components/page-header";
import { Stat } from "@/components/stat";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { backendFetch } from "@/lib/backend";
import { cents, centsPrecise } from "@/lib/format";
import { ORDER_STATE } from "@/lib/labels";
import type { DashboardResponse, OrdersResponse, SimOrder } from "@/lib/types";
import { cn } from "@/lib/utils";

function dollars(x: number | null): string {
  return x === null ? "–" : `${x < 0 ? "−" : x > 0 ? "+" : ""}$${Math.abs(x).toFixed(2)}`;
}

const tone = (x: number | null) => (x === null ? "" : x > 0 ? "text-good" : x < 0 ? "text-destructive" : "");

export default async function ResultsPage() {
  const [res, dash] = await Promise.all([backendFetch("/api/orders?scope=all&limit=100"), backendFetch("/api/dashboard")]);
  const scores = dash.ok ? ((await dash.json()) as DashboardResponse) : null;
  return (
    <>
      <PageHeader
        title="Results"
        description={
          <>
            Simulated orders and what they would have paid once the game ended. Nothing was sent to Kalshi. How the forecasts compare with the Kalshi price is on the{" "}
            <Link href="/dashboard" className="text-primary underline underline-offset-4">
              Dashboard
            </Link>
            .
          </>
        }
      />
      {!res.ok ? (
        <Alert variant="destructive">
          <AlertTitle>Orders could not be loaded</AlertTitle>
          <AlertDescription>The server answered with HTTP {res.status}. Reload the page to try again.</AlertDescription>
        </Alert>
      ) : (
        <Orders data={(await res.json()) as OrdersResponse} scores={scores} />
      )}
    </>
  );
}

function Orders({ data, scores }: { data: OrdersResponse; scores: DashboardResponse | null }) {
  const done = data.orders.filter((o) => o.state === "placed" || o.state === "settled");
  const chosen = scores?.chosen_side;
  const flagged = scores?.flagged;
  return (
    <>
      <div className="mb-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Stat
          label="Simulated orders settled"
          value={data.totals.settled}
          sub={`${data.totals.won} won · paper result ${dollars(data.totals.paper_result)}`}
        />
        {scores && chosen && flagged ? (
          <>
            <Stat
              label="Chosen side at the ask"
              value={centsPrecise(chosen.average_result)}
              sub={`average per contract after fees · ${chosen.bets} bets (the side we rated higher, bought at the ask price)`}
            />
            <Stat
              label="Flagged bets"
              value={`${flagged.won} / ${flagged.bets}`}
              sub={flagged.bets === 0 ? "none yet" : `won · average ${centsPrecise(flagged.average_result)} per contract${flagged.too_few ? " (too few to read)" : ""}`}
            />
          </>
        ) : (
          <p className="self-center text-sm text-muted-foreground sm:col-span-2">The scores of the forecasts could not be read; they are on the Dashboard.</p>
        )}
      </div>
      {done.length === 0 ? (
        <p className="text-muted-foreground">
          No simulated order has been placed yet. Prepare one from the{" "}
          <Link href="/opportunities" className="text-primary underline underline-offset-4">
            Opportunities
          </Link>{" "}
          page and approve it on the Approval page.
        </p>
      ) : (
        <div className="rounded-xl border bg-card p-1">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Placed</TableHead>
                <TableHead>Game</TableHead>
                <TableHead>Bet</TableHead>
                <TableHead className="text-right">Price</TableHead>
                <TableHead className="text-right">Fee</TableHead>
                <TableHead className="text-right">Paper result</TableHead>
                <TableHead>Status</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {done.map((o) => (
                <OrderRow key={o.id} o={o} />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <p className="mt-4 text-sm text-muted-foreground">These are simulations: no order was sent to Kalshi, and a handful of orders says almost nothing about whether the system works.</p>
    </>
  );
}

function OrderRow({ o }: { o: SimOrder }) {
  const ticket = o.legs.length > 1;
  return (
    <TableRow className="align-top">
      <TableCell className="whitespace-normal">
        <LocalTime iso={o.placed_at} />
      </TableCell>
      <TableCell className="min-w-40 whitespace-normal font-semibold">{ticket ? `Ticket of ${o.legs.length} legs` : o.title}</TableCell>
      <TableCell className="min-w-56 whitespace-normal">
        {ticket ? (
          <ul className="grid gap-0.5">
            {o.legs.map((g) => (
              <li key={g.market_ticker}>
                {g.title}: “{g.side}” on {g.outcome} at {cents(g.fill_price)} {g.won === null ? "(not known yet)" : g.won ? "(won)" : "(lost)"}
              </li>
            ))}
          </ul>
        ) : (
          <>
            {o.fill_contracts} × “{o.side}” on {o.outcome}
          </>
        )}
        {ticket ? <div className="mt-1 text-sm text-muted-foreground">{o.fill_contracts} tickets</div> : null}
      </TableCell>
      <TableCell className="text-right tabular-nums">{cents(o.fill_price)}</TableCell>
      <TableCell className="text-right tabular-nums">${o.fill_fee?.toFixed(2)}</TableCell>
      <TableCell className={cn("text-right font-bold tabular-nums", tone(o.paper_result))}>
        {o.paper_result === null ? <span className="font-normal text-muted-foreground">known when the game ends</span> : dollars(o.paper_result)}
      </TableCell>
      <TableCell className="whitespace-normal">
        <div className="flex flex-wrap gap-1.5">
          <Badge variant="outline">{ORDER_STATE[o.state]}</Badge>
          {o.state === "settled" ? (
            <Badge className={o.won === null ? "bg-secondary text-secondary-foreground" : o.won ? "bg-good-soft text-good" : "bg-destructive/10 text-destructive"}>
              {o.won === null ? "Returned" : o.won ? "Won" : "Lost"}
            </Badge>
          ) : null}
        </div>
      </TableCell>
      <TableCell>
        <Link href={`/prediction/${o.run_id}`} className="text-primary underline underline-offset-4">
          Open
        </Link>
      </TableCell>
    </TableRow>
  );
}
