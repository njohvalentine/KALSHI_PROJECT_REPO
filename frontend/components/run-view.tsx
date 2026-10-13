"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { EvidenceSection, PagesSection } from "@/components/evidence";
import { ForecastersSection } from "@/components/forecasters";
import { PredictionSection } from "@/components/prediction-table";
import { StatusBadge } from "@/components/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { dateTime, duration, money } from "@/lib/format";
import { COST_LABEL, STAGES } from "@/lib/labels";
import { isActive, type Run } from "@/lib/types";

const POLL_MS = 3000;

function Progress({ stage }: { stage: string | null }) {
  const current = Math.max(STAGES.findIndex((s) => s.key === stage), 0);
  return (
    <ol className="mt-2 grid gap-1 text-sm" aria-label="Progress">
      {STAGES.map((s, i) => (
        <li key={s.key} className={i === current ? "font-medium text-foreground" : i < current ? "text-good" : "text-muted-foreground"}>
          {i < current ? "✓ " : i === current ? "→ " : "○ "}
          {s.label}
          {i === current ? " (now)" : ""}
        </li>
      ))}
    </ol>
  );
}

export function RunView({ initial }: { initial: Run }) {
  const router = useRouter();
  const [run, setRun] = useState<Run>(initial);
  const [pollError, setPollError] = useState(false);

  useEffect(() => {
    if (!isActive(run.status)) return;
    const timer = setInterval(async () => {
      try {
        const res = await fetch(`/api/runs/${run.id}`, { cache: "no-store" });
        if (res.status === 401) return router.replace("/login");
        if (!res.ok) throw new Error(String(res.status));
        setRun(await res.json());
        setPollError(false);
      } catch {
        setPollError(true); // keep trying; the run itself continues on the server
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [run.id, run.status, router]);

  const errors = run.result?.errors ?? [];
  const angles = run.plan?.angles ?? [];

  return (
    <>
      {/* The forecast and the comparison use the full width: the table has six columns. */}
      {!isActive(run.status) ? <PredictionSection run={run} /> : null}
      {!isActive(run.status) ? <ForecastersSection run={run} /> : null}
      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div>
        {isActive(run.status) ? (
          <Alert className="mb-6">
            <AlertTitle>{run.status === "queued" ? "Waiting to start" : "Working on this game"}</AlertTitle>
            <AlertDescription>
              This page updates by itself. You can leave it; the run keeps going and the result stays here.
              {pollError ? " The latest update could not be loaded; trying again." : ""}
              {run.status === "running" ? <Progress stage={run.stage} /> : null}
            </AlertDescription>
          </Alert>
        ) : null}
        {run.status === "failed" ? (
          <Alert variant="destructive" className="mb-6">
            <AlertTitle>This run failed</AlertTitle>
            <AlertDescription>{run.error ?? "No reason was recorded."}</AlertDescription>
          </Alert>
        ) : null}

        <EvidenceSection run={run} />
        <PagesSection pages={run.pages ?? []} />

        {angles.length > 0 ? (
          <section className="mb-8">
            <h2 className="mb-3 text-xl font-semibold tracking-tight">What was researched</h2>
            <ul className="grid gap-3">
              {angles.map((a) => (
                <li key={a.name}>
                  <span className="font-medium">{a.name}</span>
                  <span className="text-muted-foreground">: {a.question}</span>
                </li>
              ))}
            </ul>
            {run.plan && run.plan.cut_angles > 0 ? (
              <p className="mt-2 text-sm text-muted-foreground">
                The planner proposed {run.plan.cut_angles} more angle(s); they were dropped to stay within the researcher limit.
              </p>
            ) : null}
          </section>
        ) : null}

        {errors.length > 0 ? (
          <section className="mb-8">
            <h2 className="mb-3 text-xl font-semibold tracking-tight">Angles that did not finish</h2>
            <ul className="grid gap-2">
              {errors.map((e) => (
                <li key={e.angle}>
                  <span className="font-medium">{e.angle}</span>
                  <span className="text-muted-foreground">: {e.error}</span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>

      <aside className="rounded-xl border bg-card p-6" aria-label="Run details">
        <dl>
          {[
            ["Status", <StatusBadge key="s" status={run.status} />],
            ["Started", dateTime(run.started_at ?? run.created_at)],
            ["Time taken", duration(run.started_at, run.finished_at)],
            ["Angles", String(angles.length)],
            ["Cited lines", String(run.sourced_claims)],
            ["Reached", run.status === "done" ? "All steps" : (STAGES.find((x) => x.key === run.stage)?.label ?? "–")],
            ["Searches", String(run.search_calls)],
            ["Tokens in / out", `${run.input_tokens.toLocaleString("en-US")} / ${run.output_tokens.toLocaleString("en-US")}`],
            ["Cost", money(run.cost_usd)],
          ].map(([label, value]) => (
            <div key={String(label)} className="flex justify-between gap-4 border-b py-2.5 last:border-b-0">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="text-right font-medium">{value}</dd>
            </div>
          ))}
        </dl>
        {run.costs && Object.keys(run.costs).length > 0 ? (
          <div className="mt-4">
            <h3 className="mb-1 text-sm font-medium">Where the cost went</h3>
            <dl className="text-sm">
              {Object.entries(run.costs).map(([key, value]) => (
                <div key={key} className="flex justify-between gap-4 py-0.5">
                  <dt className="text-muted-foreground">{COST_LABEL[key] ?? key}</dt>
                  <dd className="tabular-nums">{money(value)}</dd>
                </div>
              ))}
            </dl>
          </div>
        ) : null}
        {run.cost_usd === null && run.cost_note ? <p className="mt-3 text-sm text-muted-foreground">{run.cost_note}</p> : null}
        {run.over_budget ? <p className="mt-3 text-sm text-warn">This run cost more than the warning level set for one run.</p> : null}
      </aside>
      </div>
    </>
  );
}
