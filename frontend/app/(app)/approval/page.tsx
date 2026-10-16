import Link from "next/link";
import { LocalTime } from "@/components/local-time";
import { OrderActions } from "@/components/order-actions";
import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { backendFetch } from "@/lib/backend";
import { cents, gapCents, pct } from "@/lib/format";
import { CHECK_NAME, ORDER_STATE } from "@/lib/labels";
import type { OrdersResponse, SimOrder } from "@/lib/types";

function orderSentence(o: SimOrder): string {
  if (o.legs.length > 1) {
    return `Buy ${o.contracts} ticket${o.contracts === 1 ? "" : "s"} of ${o.legs.length} legs at ${cents(o.price)} each. It pays only if every leg wins. Cost up to $${o.max_cost.toFixed(2)} including a fee of about $${o.fee_estimate.toFixed(2)}.`;
  }
  return `Buy ${o.contracts} “${o.side}” contract${o.contracts === 1 ? "" : "s"} on ${o.outcome} (${o.title}) at ${cents(o.price)} each. Cost up to $${o.max_cost.toFixed(2)} including a fee of about $${o.fee_estimate.toFixed(2)}.`;
}

function Waiting({ order }: { order: SimOrder }) {
  const checks = order.checks ?? [];
  const blocked = checks.some((c) => c.blocking && !c.ok);
  return (
    <li className="rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <Link href={`/prediction/${order.run_id}`} className="font-medium text-primary underline-offset-4 hover:underline">
          {order.title}
        </Link>
        <Badge variant="outline">{ORDER_STATE[order.state]}</Badge>
      </div>
      <p className="mt-2 font-medium">{orderSentence(order)}</p>
      {order.legs.length > 1 ? (
        <ol className="mt-2 grid gap-1 text-sm" aria-label="Games on the ticket">
          {order.legs.map((g) => (
            <li key={g.market_ticker}>
              {g.position + 1}. <Link href={`/prediction/${g.run_id}`} className="text-primary underline-offset-4 hover:underline">{g.title}</Link>: “{g.side}” on {g.outcome} at {cents(g.price)} (our estimate {pct(g.our_probability)})
            </li>
          ))}
        </ol>
      ) : null}
      <p className="mt-1 text-sm text-muted-foreground">
        Our probability {pct(order.our_probability)} against the market’s {pct(order.price)}; gap after fees {gapCents(order.gap)} when it was prepared. Expires{" "}
        <LocalTime iso={order.expires_at} />. This is a simulation: nothing is sent to Kalshi.
      </p>
      {checks.length > 0 ? (
        <ul className="mt-3 grid gap-1 text-sm" aria-label="Checks">
          {checks.map((c) => (
            <li key={`${c.leg}-${c.name}`} className={c.ok ? "text-good" : c.blocking ? "text-destructive" : "text-warn"}>
              {c.ok ? "✓" : c.blocking ? "✗" : "!"} {c.leg === null || order.legs.length < 2 ? "" : `Leg ${c.leg + 1}: `}{CHECK_NAME[c.name] ?? c.name}
              <span className="text-muted-foreground"> — {c.detail}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <OrderActions order={order} blocked={blocked} />
    </li>
  );
}

export default async function ApprovalPage() {
  const openRes = await backendFetch("/api/orders?scope=open");
  if (!openRes.ok) {
    return (
      <>
        <PageHeader title="Approve bet" description="Orders waiting for a person to approve or reject them." />
        <Alert variant="destructive">
          <AlertTitle>Orders could not be loaded</AlertTitle>
          <AlertDescription>The server answered with HTTP {openRes.status}. Reload the page to try again.</AlertDescription>
        </Alert>
      </>
    );
  }
  const open = ((await openRes.json()) as OrdersResponse).orders;
  // The checks read today's prices, so each waiting order is loaded on its own.
  const detailed = await Promise.all(
    open.map(async (o) => {
      const r = await backendFetch(`/api/orders/${o.id}`);
      return r.ok ? ((await r.json()) as SimOrder) : o;
    }),
  );
  const recentRes = await backendFetch("/api/orders?scope=recent&limit=15");
  const recent = recentRes.ok ? ((await recentRes.json()) as OrdersResponse).orders.filter((o) => o.state !== "proposed" && o.state !== "approved") : [];

  return (
    <>
      <PageHeader
        title="Approve bet"
        description="A person approves or rejects every order here, and approved orders are placed in a simulation in a separate step. No order is ever sent to Kalshi."
      />
      <section aria-labelledby="waiting-heading" className="mb-8">
        <h2 id="waiting-heading" className="mb-3 text-xl font-semibold tracking-tight">
          Waiting
        </h2>
        {detailed.length === 0 ? (
          <p className="text-muted-foreground">
            Nothing is waiting. Prepare an order from the{" "}
            <Link href="/opportunities" className="text-primary underline underline-offset-4">
              Opportunities
            </Link>{" "}
            page.
          </p>
        ) : (
          <ul className="grid gap-3">
            {detailed.map((o) => (
              <Waiting key={o.id} order={o} />
            ))}
          </ul>
        )}
      </section>
      <section aria-labelledby="recent-heading">
        <h2 id="recent-heading" className="mb-3 text-xl font-semibold tracking-tight">
          Recent orders
        </h2>
        {recent.length === 0 ? (
          <p className="text-sm text-muted-foreground">None yet.</p>
        ) : (
          <div className="rounded-xl border bg-card p-1">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Order</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Why</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recent.map((o) => (
                  <TableRow key={o.id} className="align-top">
                    <TableCell className="whitespace-normal">
                      <LocalTime iso={o.created_at} />
                    </TableCell>
                    <TableCell className="min-w-72 whitespace-normal">{orderSentence(o)}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{ORDER_STATE[o.state]}</Badge>
                    </TableCell>
                    <TableCell className="whitespace-normal text-muted-foreground">{o.reason ?? ""}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>
    </>
  );
}
