"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { SimOrder } from "@/lib/types";

async function call(path: string, body?: object) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Requested-With": "web" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  return { res, data };
}

/** Approve, reject and place buttons. Each is a person's explicit press; nothing here is automatic. */
export function OrderActions({ order, blocked }: { order: SimOrder; blocked: boolean }) {
  const router = useRouter();
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");

  async function act(name: string, path: string, body?: object) {
    setError(null);
    setPending(name);
    try {
      const { res, data } = await call(path, body);
      if (res.status === 401) return router.replace("/login");
      if (!res.ok) {
        const detail = data.detail;
        setError(typeof detail === "string" ? detail : (detail?.message ?? `Failed (HTTP ${res.status}).`));
      }
      router.refresh();
    } catch {
      setError("The server could not be reached.");
    } finally {
      setPending(null);
      setRejecting(false);
    }
  }

  return (
    <div className="mt-3">
      <div className="flex flex-wrap items-center gap-2">
        {order.state === "proposed" ? (
          <Button size="sm" disabled={pending !== null || blocked} onClick={() => act("approve", `/api/orders/${order.id}/approve`)} title={blocked ? "A check failed, see above" : undefined}>
            {pending === "approve" ? "Approving…" : "Approve"}
          </Button>
        ) : null}
        {order.state === "approved" ? (
          <Button size="sm" disabled={pending !== null} onClick={() => act("place", `/api/orders/${order.id}/place`)}>
            {pending === "place" ? "Placing…" : "Place in the simulation"}
          </Button>
        ) : null}
        {order.state === "proposed" || order.state === "approved" ? (
          rejecting ? (
            <>
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Why (optional)"
                aria-label="Reason for rejecting"
                maxLength={300}
                className="h-8 w-56 rounded-lg border bg-card px-2 text-sm"
              />
              <Button size="sm" variant="outline" disabled={pending !== null} onClick={() => act("reject", `/api/orders/${order.id}/reject`, { reason: reason || null })}>
                Confirm reject
              </Button>
            </>
          ) : (
            <Button size="sm" variant="outline" disabled={pending !== null} onClick={() => setRejecting(true)}>
              Reject
            </Button>
          )
        ) : null}
      </div>
      {error ? <p role="alert" className="mt-2 text-sm text-destructive">{error}</p> : null}
    </div>
  );
}
