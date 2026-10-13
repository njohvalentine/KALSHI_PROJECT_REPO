"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";

/** Prepares a SIMULATED order. It only creates a proposal that a person must approve on the Approval page. */
export function PrepareOrder({ runId, marketTicker }: { runId: string; marketTicker: string }) {
  const router = useRouter();
  const [contracts, setContracts] = useState("1");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function prepare() {
    setError(null);
    setPending(true);
    try {
      const res = await fetch("/api/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Requested-With": "web" },
        body: JSON.stringify({ run_id: runId, market_ticker: marketTicker, contracts: Number.parseInt(contracts, 10) || 0 }),
      });
      if (res.status === 201) return router.push("/approval");
      if (res.status === 401) return router.replace("/login");
      const body = await res.json().catch(() => ({}));
      const detail = body.detail;
      if (res.status === 409 && detail?.order_id) return router.push("/approval");
      setError(typeof detail === "string" ? detail : (detail?.message ?? `Could not prepare (HTTP ${res.status}).`));
    } catch {
      setError("The server could not be reached.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col items-start gap-1">
      <div className="flex items-center gap-2">
        <label className="text-sm text-muted-foreground" htmlFor={`n-${marketTicker}`}>
          Contracts
        </label>
        <input
          id={`n-${marketTicker}`}
          type="number"
          min={1}
          max={1000}
          value={contracts}
          onChange={(e) => setContracts(e.target.value)}
          className="h-8 w-16 rounded-lg border bg-card px-2 text-sm"
        />
        <Button size="sm" variant="outline" onClick={prepare} disabled={pending} title="Creates a simulated order for a person to approve. Nothing is sent to Kalshi.">
          {pending ? "Preparing…" : "Prepare order"}
        </Button>
      </div>
      {error ? <span role="alert" className="max-w-[44ch] text-xs text-destructive">{error}</span> : null}
    </div>
  );
}
