import Link from "next/link";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { backendFetch } from "@/lib/backend";
import { dateTime, money } from "@/lib/format";
import type { RunSummary } from "@/lib/types";

export default async function PredictionPage() {
  const res = await backendFetch("/api/runs?limit=30");
  const runs: RunSummary[] = res.ok ? ((await res.json()) as { runs: RunSummary[] }).runs : [];
  return (
    <>
      <PageHeader
        title="Prediction"
        description="Research runs, newest first. Start one from the Markets page. Probabilities come in a later milestone."
      />
      {!res.ok ? (
        <Alert variant="destructive">
          <AlertTitle>Runs could not be loaded</AlertTitle>
          <AlertDescription>The server answered with HTTP {res.status}. Reload the page to try again.</AlertDescription>
        </Alert>
      ) : runs.length === 0 ? (
        <p className="text-muted-foreground">
          No research yet. Open{" "}
          <Link href="/markets" className="text-primary underline underline-offset-4">
            Markets
          </Link>{" "}
          and press Analyze on a market.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="px-4 py-3">Market</TableHead>
                <TableHead className="px-4 py-3">Status</TableHead>
                <TableHead className="px-4 py-3">Started</TableHead>
                <TableHead className="px-4 py-3 text-right">Cited lines</TableHead>
                <TableHead className="px-4 py-3 text-right">Cost</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="whitespace-normal px-4 py-3.5">
                    <Link href={`/prediction/${r.id}`} className="block max-w-[46ch] font-medium text-primary underline-offset-4 hover:underline">
                      {r.event_title}
                    </Link>
                    <span className="text-sm text-muted-foreground">{r.event_ticker}</span>
                  </TableCell>
                  <TableCell className="px-4 py-3.5">
                    <StatusBadge status={r.status} />
                  </TableCell>
                  <TableCell className="px-4 py-3.5">{dateTime(r.started_at ?? r.created_at)}</TableCell>
                  <TableCell className="px-4 py-3.5 text-right tabular-nums">{r.sourced_claims}</TableCell>
                  <TableCell className="px-4 py-3.5 text-right tabular-nums">{money(r.cost_usd)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </>
  );
}
