import { AnalyzeButton } from "@/components/analyze-button";
import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { backendFetch } from "@/lib/backend";
import type { RunSummary } from "@/lib/types";

// Field names as documented by Kalshi (docs.kalshi.com, Get Markets). Not yet checked against a
// live response, so every field is read defensively and shown as a dash when missing.
type Market = {
  ticker: string;
  title?: string;
  subtitle?: string;
  close_time?: string;
  last_price_dollars?: string;
};

function percent(dollars?: string): string {
  const value = Number.parseFloat(dollars ?? "");
  return Number.isFinite(value) ? `${Math.round(value * 100)}%` : "–";
}

function closes(iso?: string): string {
  const date = iso ? new Date(iso) : null;
  return date && !Number.isNaN(date.getTime())
    ? date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
    : "–";
}

export default async function MarketsPage() {
  const res = await backendFetch("/api/markets?status=open&limit=50");
  let markets: Market[] = [];
  let error: string | null = null;
  if (res.ok) {
    markets = ((await res.json()) as { markets?: Market[] }).markets ?? [];
  } else {
    const detail = await res.json().then((b) => b.detail as string, () => "");
    error = res.status === 502 ? detail || "Kalshi could not be reached." : `The server answered with HTTP ${res.status}.`;
  }

  // Latest research run per market, to show "In progress" or "View research". If this cannot be
  // loaded the list still works; the buttons just start fresh.
  const latestRes = await backendFetch("/api/runs/latest");
  const latest = new Map<string, { id: string; status: RunSummary["status"] }>();
  if (latestRes.ok) {
    for (const r of ((await latestRes.json()) as { runs: { market_ticker: string; id: string; status: RunSummary["status"] }[] }).runs) {
      latest.set(r.market_ticker, { id: r.id, status: r.status });
    }
  }

  return (
    <>
      <PageHeader
        title="Markets"
        description="Open Kalshi markets and their current price. Press Analyze to research a market. Estimates and the comparison with the market price come in a later milestone."
      />
      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Markets could not be loaded</AlertTitle>
          <AlertDescription>{error} Reload the page to try again.</AlertDescription>
        </Alert>
      ) : markets.length === 0 ? (
        <p className="text-muted-foreground">Kalshi returned no open markets.</p>
      ) : (
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
                    <AnalyzeButton ticker={m.ticker} latest={latest.get(m.ticker) ?? null} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </>
  );
}
