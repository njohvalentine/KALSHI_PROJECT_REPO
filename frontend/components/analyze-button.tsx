"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, buttonVariants } from "@/components/ui/button";
import { isActive, type RunSummary } from "@/lib/types";

type Latest = { id: string; status: RunSummary["status"] } | null;

export function AnalyzeButton({ ticker, latest }: { ticker: string; latest: Latest }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setError(null);
    setPending(true);
    try {
      const res = await fetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Requested-With": "web" },
        body: JSON.stringify({ ticker }),
      });
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

  if (latest && isActive(latest.status)) {
    return (
      <Link href={`/prediction/${latest.id}`} className={buttonVariants({ variant: "outline", size: "sm" })}>
        In progress
      </Link>
    );
  }
  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex gap-2">
        {latest?.status === "done" ? (
          <Link href={`/prediction/${latest.id}`} className={buttonVariants({ variant: "outline", size: "sm" })}>
            View research
          </Link>
        ) : null}
        <Button size="sm" onClick={start} disabled={pending}>
          {pending ? "Starting…" : latest ? "Analyze again" : "Analyze"}
        </Button>
      </div>
      {error ? <span role="alert" className="max-w-[28ch] text-right text-xs text-destructive">{error}</span> : null}
    </div>
  );
}
