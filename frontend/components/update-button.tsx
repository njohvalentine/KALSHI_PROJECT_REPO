"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";

/** Starts a lineup update of a finished run: one researcher looks for the confirmed lineups and late team news, and the earlier checked evidence is kept. */
export function UpdateButton({ runId, hoursToStart }: { runId: string; hoursToStart: number | null }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setError(null);
    setPending(true);
    try {
      const res = await fetch(`/api/runs/${runId}/update`, { method: "POST", headers: { "X-Requested-With": "web" } });
      const body = await res.json().catch(() => ({}));
      if (res.status === 202) return router.push(`/prediction/${body.id}`);
      if (res.status === 409 && body.run_id) return router.push(`/prediction/${body.run_id}`);
      if (res.status === 401) return router.replace("/login");
      setError(typeof body.detail === "string" ? body.detail : `Could not start (HTTP ${res.status}).`);
    } catch {
      setError("The server could not be reached.");
    } finally {
      setPending(false);
    }
  }

  const early = hoursToStart !== null && hoursToStart > 3;
  return (
    <div className="mt-4 rounded-lg border bg-muted/40 p-3 text-sm" aria-label="Update with lineups">
      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" onClick={start} disabled={pending} title="One researcher, the earlier checked facts are kept. About $0.20 (estimated).">
          {pending ? "Starting…" : "Update with lineups"}
        </Button>
        <span className="text-muted-foreground">
          Looks for the confirmed lineups and late team news and makes a new forecast. About $0.20 (estimated); it counts against the daily update limit, not the game limit.
        </span>
      </div>
      {early ? (
        <p className="mt-2 text-warn">
          The game starts in about {Math.round(hoursToStart!)} hours. Lineups are usually published about an hour before the start, so an update now will probably find only expected lineups.
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="mt-2 text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
