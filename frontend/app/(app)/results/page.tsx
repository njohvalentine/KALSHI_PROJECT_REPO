import Link from "next/link";
import { LocalTime } from "@/components/local-time";
import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { backendFetch } from "@/lib/backend";
import { cents } from "@/lib/format";
import { ORDER_STATE } from "@/lib/labels";
import type { OrdersResponse } from "@/lib/types";

function dollars(x: number | null): string {
  return x === null ? "–" : `${x < 0 ? "−" : x > 0 ? "+" : ""}$${Math.abs(x).toFixed(2)}`;
}

export default async function ResultsPage() {
  const res = await backendFetch("/api/orders?scope=all&limit=100");
  return (
    <>
      <PageHeader
        title="Results"
        description="Simulated orders and what they would have paid once the game ended. The accuracy of our forecasts against the market is printed by the command score-records (see the run guide); it needs about 30 finished games before it means anything."
      />
      {!res.ok ? (
        <Alert variant="destructive">
          <AlertTitle>Orders could not be loaded</AlertTitle>
          <AlertDescription>The server answered with HTTP {res.status}. Reload the page to try again.</AlertDescription>
        </Alert>
      ) : null}
      {res.ok ? <Orders data={(await res.json()) as OrdersResponse} /> : null}
    </>
  );
}

function Orders({ data }: { data: OrdersResponse }) {
  const done = data.orders.filter((o) => o.state === "placed" || o.state === "settled");
  return (
    <>
      <p className="mb-4 text-sm text-muted-foreground">
        {data.totals.settled} settled simulated order{data.totals.settled === 1 ? "" : "s"}, {data.totals.won} won, paper result {dollars(data.totals.paper_result)}. These are simulations: no order was
        sent to Kalshi, and a handful of orders says almost nothing about whether the system works.
      </p>
      {done.length === 0 ? (
        <p className="text-muted-foreground">
          No simulated order has been placed yet. Prepare one from the{" "}
          <Link href="/opportunities" className="text-primary underline underline-offset-4">
            Opportunities
          </Link>{" "}
          page and approve it on the Approval page.
        </p>
      ) : (
        <ul className="grid gap-2">
          {done.map((o) => (
            <li key={o.id} className="rounded-xl border bg-card p-3 text-sm">
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <Badge variant="outline">{ORDER_STATE[o.state]}</Badge>
                {o.state === "settled" ? <Badge className={o.won === null ? "bg-secondary text-secondary-foreground" : o.won ? "bg-good-soft text-good" : "bg-destructive/10 text-destructive"}>{o.won === null ? "Returned" : o.won ? "Won" : "Lost"}</Badge> : null}
                <span className="text-muted-foreground">
                  placed <LocalTime iso={o.placed_at} />
                </span>
                <Link href={`/prediction/${o.run_id}`} className="text-primary underline underline-offset-4">
                  Open
                </Link>
              </div>
              {o.legs.length > 1 ? (
                <ul className="mb-1 grid gap-0.5">
                  {o.legs.map((g) => (
                    <li key={g.market_ticker}>
                      {g.title}: “{g.side}” on {g.outcome} at {cents(g.fill_price)} {g.won === null ? "(not known yet)" : g.won ? "(won)" : "(lost)"}
                    </li>
                  ))}
                </ul>
              ) : null}
              <p>
                {o.legs.length > 1 ? `Ticket of ${o.legs.length} legs` : o.title}: {o.fill_contracts} {o.legs.length > 1 ? "tickets" : `“${o.side}” on ${o.outcome}`} at {cents(o.fill_price)}, fee ${o.fill_fee?.toFixed(2)}. {o.paper_result === null ? "The result is known when the game ends." : `Paper result ${dollars(o.paper_result)}.`}
              </p>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
