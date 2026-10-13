import Link from "next/link";
import { notFound } from "next/navigation";
import { PageHeader } from "@/components/page-header";
import { RunView } from "@/components/run-view";
import { backendFetch } from "@/lib/backend";
import type { Run } from "@/lib/types";

export default async function RunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const res = await backendFetch(`/api/runs/${encodeURIComponent(runId)}`);
  if (res.status === 404) notFound();
  if (!res.ok) throw new Error(`The run could not be loaded (HTTP ${res.status})`);
  const run: Run = await res.json();
  return (
    <>
      <p className="mb-2 text-sm text-muted-foreground">
        <Link href="/prediction" className="text-primary underline underline-offset-4">
          All runs
        </Link>{" "}
        / {run.event_ticker}
      </p>
      <PageHeader title={run.event_title} description="Our forecast for this game, how it compares with the market, and the research and sources behind it." />
      <RunView initial={run} />
    </>
  );
}
