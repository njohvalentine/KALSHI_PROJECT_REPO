"use client";

import { useRouter } from "next/navigation";
import { createContext, useContext, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cents, pct } from "@/lib/format";

export type TicketLeg = { runId: string; eventTicker: string; marketTicker: string; title: string; market: string; side: "yes" | "no"; price: number; probability: number };
type Ctx = { legs: TicketLeg[]; toggle: (leg: TicketLeg) => void };
const TicketContext = createContext<Ctx | null>(null);

/** Holds the legs a person has picked on the Opportunities page. Nothing is sent until Prepare ticket is pressed. */
export function TicketProvider({ children, maxLegs }: { children: ReactNode; maxLegs: number }) {
  const [legs, setLegs] = useState<TicketLeg[]>([]);
  const toggle = (leg: TicketLeg) =>
    setLegs((cur) => {
      if (cur.some((l) => l.eventTicker === leg.eventTicker && l.marketTicker === leg.marketTicker)) return cur.filter((l) => l.eventTicker !== leg.eventTicker);
      return cur.length >= maxLegs ? cur : [...cur.filter((l) => l.eventTicker !== leg.eventTicker), leg]; // one leg per game
    });
  return (
    <TicketContext.Provider value={{ legs, toggle }}>
      {children}
      <TicketPanel maxLegs={maxLegs} />
    </TicketContext.Provider>
  );
}

export function AddToTicket({ leg }: { leg: TicketLeg }) {
  const ctx = useContext(TicketContext);
  if (!ctx) return null;
  const on = ctx.legs.some((l) => l.marketTicker === leg.marketTicker);
  return (
    <Button size="sm" variant={on ? "default" : "outline"} onClick={() => ctx.toggle(leg)} aria-pressed={on} title="Adds this game to a ticket: one bet that pays only if every game on it wins.">
      {on ? "On the ticket" : "Add to ticket"}
    </Button>
  );
}

function TicketPanel({ maxLegs }: { maxLegs: number }) {
  const ctx = useContext(TicketContext)!;
  const router = useRouter();
  const [contracts, setContracts] = useState("1");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { legs } = ctx;
  if (legs.length === 0) return null;
  const price = legs.reduce((a, l) => a * l.price, 1);
  const probability = legs.reduce((a, l) => a * l.probability, 1);

  async function prepare() {
    setError(null);
    setPending(true);
    try {
      const res = await fetch("/api/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Requested-With": "web" },
        body: JSON.stringify({ legs: legs.map((l) => ({ run_id: l.runId, market_ticker: l.marketTicker })), contracts: Number.parseInt(contracts, 10) || 0 }),
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
    <section aria-label="Ticket" className="sticky bottom-3 mt-6 rounded-xl border bg-card p-4 shadow-md">
      <h2 className="text-lg font-semibold tracking-tight">Ticket: {legs.length} game{legs.length === 1 ? "" : "s"}</h2>
      <ul className="mt-2 grid gap-1 text-sm">
        {legs.map((l) => (
          <li key={l.marketTicker} className="flex flex-wrap items-center justify-between gap-2">
            <span>
              {l.title}: “{l.side}” on {l.market} at {cents(l.price)} (our estimate {pct(l.probability)})
            </span>
            <Button size="sm" variant="ghost" onClick={() => ctx.toggle(l)}>
              Remove
            </Button>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-sm">
        The ticket pays only if <strong>every</strong> game wins. Together: price {cents(price)} each, our chance {pct(probability)}.
      </p>
      <p className="mt-1 text-sm text-muted-foreground">
        The price is the legs multiplied, as in the simulation. A real combo on Kalshi is quoted on request and is usually worse. Each game adds the model’s error, so more games means a less
        certain ticket (at most {maxLegs}).{legs.length >= 3 ? " Three or more games: take extra care." : ""}
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <label className="text-sm text-muted-foreground" htmlFor="ticket-contracts">Contracts</label>
        <input id="ticket-contracts" type="number" min={1} max={1000} value={contracts} onChange={(e) => setContracts(e.target.value)} className="h-8 w-16 rounded-lg border bg-card px-2 text-sm" />
        <Button size="sm" onClick={prepare} disabled={pending} title="Creates a simulated ticket for a person to approve. Nothing is sent to Kalshi.">
          {pending ? "Preparing…" : "Prepare ticket"}
        </Button>
      </div>
      {error ? <p role="alert" className="mt-2 text-sm text-destructive">{error}</p> : null}
    </section>
  );
}
