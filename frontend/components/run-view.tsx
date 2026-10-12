"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { dateTime, duration, host, money } from "@/lib/format";
import { isActive, type Claim, type Run } from "@/lib/types";

const POLL_MS = 3000;

function ClaimItem({ claim }: { claim: Claim }) {
  return (
    <li className="border-b py-4 last:border-b-0">
      <p className="mb-1.5 font-medium">{claim.text}</p>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
        {claim.kind === "sourced" ? <Badge className="bg-secondary text-secondary-foreground">Cited</Badge> : null}
        {claim.kind === "uncited" ? <Badge className="bg-warn-soft text-warn">No source given</Badge> : null}
        {claim.kind === "none" ? <Badge variant="outline">Nothing found</Badge> : null}
        {claim.sources.map((s) => (
          <a key={s.url} href={s.url} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-4">
            {s.title || host(s.url)} <span className="text-muted-foreground">({host(s.url)})</span>
          </a>
        ))}
      </div>
    </li>
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

  const findings = run.result?.findings ?? [];
  const errors = run.result?.errors ?? [];
  const angles = run.plan?.angles ?? [];

  return (
    <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div>
        {isActive(run.status) ? (
          <Alert className="mb-6">
            <AlertTitle>{run.status === "queued" ? "Waiting to start" : "Researching this game"}</AlertTitle>
            <AlertDescription>
              This page updates by itself. You can leave it; the run keeps going and the result stays here.
              {pollError ? " The latest update could not be loaded; trying again." : ""}
            </AlertDescription>
          </Alert>
        ) : null}
        {run.status === "failed" ? (
          <Alert variant="destructive" className="mb-6">
            <AlertTitle>This run failed</AlertTitle>
            <AlertDescription>{run.error ?? "No reason was recorded."}</AlertDescription>
          </Alert>
        ) : null}

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

        {findings.map((f) => (
          <section key={f.angle} className="mb-8">
            <h2 className="mb-1 text-xl font-semibold tracking-tight">{f.angle}</h2>
            <p className="mb-2 text-sm text-muted-foreground">{f.question}</p>
            <ul>
              {f.claims.map((c, i) => (
                <ClaimItem key={i} claim={c} />
              ))}
            </ul>
          </section>
        ))}

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

        {run.status === "done" ? (
          <p className="text-sm text-muted-foreground">
            “Cited” means the search tool attached a source link to the line. The sources have not been checked against the pages yet,
            and there is no probability yet. Both come in a later milestone.
          </p>
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
        {run.cost_usd === null && run.cost_note ? <p className="mt-3 text-sm text-muted-foreground">{run.cost_note}</p> : null}
        {run.over_budget ? <p className="mt-3 text-sm text-warn">This run cost more than the warning level set for one run.</p> : null}
      </aside>
    </div>
  );
}
