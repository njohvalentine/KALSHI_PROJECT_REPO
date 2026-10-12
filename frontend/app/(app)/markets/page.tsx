import { AnalyzeButton } from "@/components/analyze-button";
import { Suspense } from "react";
import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { backendFetch } from "@/lib/backend";
import type { RunSummary } from "@/lib/types";

// Field names as documented by Kalshi (docs.kalshi.com, Get Markets). Not yet checked against a
// live response, so every field is read defensively and shown as a dash when missing.
type Market = {
  ticker: string;
  event_ticker: string;
  title?: string;
  subtitle?: string;
  close_time?: string;
  last_price_dollars?: string;
};

function percent(dollars?: string): string {
  const value = Number.parseFloat(dollars ?? "");
  // A traded contract cannot have a last price of zero (the lowest price is 1 cent), so zero or a
  // missing price means nobody has traded it yet. Showing "0%" would claim the market priced it at 0.
  return Number.isFinite(value) && value > 0 ? `${Math.round(value * 100)}%` : "No trades yet";
}

function closes(iso?: string): string {
  const date = iso ? new Date(iso) : null;
  return date && !Number.isNaN(date.getTime())
    ? date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
    : "–";
}

async function MarketsTable() {
  // Both lookups run together. The latest-run lookup only decorates the buttons; if it fails the
  // list still works and the buttons simply start fresh.
  const [res, latestRes] = await Promise.all([
    backendFetch("/api/markets?status=open&limit=50"),
    backendFetch("/api/runs/latest"),
  ]);
  let markets: Market[] = [];
  let error: string | null = null;
  if (res.ok) {
    markets = ((await res.json()) as { markets?: Market[] }).markets ?? [];
  } else {
    const detail = await res.json().then((b) => b.detail as string, () => "");
    error = res.status === 502 ? detail || "Kalshi could not be reached." : `The server answered with HTTP ${res.status}.`;
  }
  const latest = new Map<string, { id: string; status: RunSummary["status"] }>();
  if (latestRes.ok) {
    for (const r of ((await latestRes.json()) as { runs: { event_ticker: string; id: string; status: RunSummary["status"] }[] }).runs) {
      latest.set(r.event_ticker, { id: r.id, status: r.status });
    }
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Markets could not be loaded</AlertTitle>
        <AlertDescription>{error} Reload the page to try again.</AlertDescription>
      </Alert>
    );
  }
  if (markets.length === 0) return <p className="text-muted-foreground">Kalshi returned no open markets.</p>;
  return (
    <div className="overflow-x-auto rounded-xl border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="px-4 py-3">Question</TableHead>
            <TableHead className="px-4 py-3">Closes</TableHead>
            <TableHead className="px-4 py-3 text-right">Market price</TableHead>
            <TableHead className="px-4 py-3 text-right">Research</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {markets.map((m) => (
            <TableRow key={m.ticker}>
              <TableCell className="whitespace-normal px-4 py-3.5">
                <span className="block max-w-[46ch] font-medium">{m.title ?? m.ticker}</span>
                {m.subtitle ? <span className="text-sm text-muted-foreground">{m.subtitle}</span> : null}
              </TableCell>
              <TableCell className="px-4 py-3.5">{closes(m.close_time)}</TableCell>
              <TableCell className="px-4 py-3.5 text-right tabular-nums">{percent(m.last_price_dollars)}</TableCell>
              <TableCell className="px-4 py-3.5 text-right">
                <AnalyzeButton eventTicker={m.event_ticker} latest={latest.get(m.event_ticker) ?? null} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function MarketsLoading() {
  return (
    <div role="status" aria-live="polite">
      <p className="mb-3 text-muted-foreground">Loading markets from Kalshi…</p>
      <div className="overflow-hidden rounded-xl border bg-card">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="flex gap-6 border-b px-4 py-5 last:border-b-0">
            <div className="h-4 flex-1 rounded bg-muted motion-safe:animate-pulse" />
            <div className="h-4 w-24 rounded bg-muted motion-safe:animate-pulse" />
            <div className="h-4 w-16 rounded bg-muted motion-safe:animate-pulse" />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function MarketsPage() {
  // The title shows at once; the table streams in when Kalshi has answered.
  return (
    <>
      <PageHeader
        title="Markets"
        description="Open Kalshi markets and their current price. Press Analyze to research a market. Estimates and the comparison with the market price come in a later milestone."
      />
      <Suspense fallback={<MarketsLoading />}>
        <MarketsTable />
      </Suspense>
    </>
  );
}
