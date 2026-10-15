"use client";

import { useRouter } from "next/navigation";
import { createContext, useContext, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cents, pct } from "@/lib/format";

export type TicketLeg = { runId: string; eventTicker: string; marketTicker: string; title: string; market: string; side: "yes" | "no"; price: number; probability: number; flagged?: boolean };
type Ctx = { legs: TicketLeg[]; toggle: (leg: TicketLeg) => void };
const STORE = "ticket-legs";
// Kalshi groups the markets of one question in one event (the winner, one total, both teams to score); a ticket takes one leg from each group.
const groupOf = (marketTicker: string) => marketTicker.slice(0, marketTicker.lastIndexOf("-"));
const TicketContext = createContext<Ctx | null>(null);

/** Holds the legs a person has picked, on every page, until the ticket is prepared. Nothing is sent until Prepare ticket is pressed. */
// The legs live in the browser's session storage, so they stay while the person moves between pages. If storage is blocked the ticket still works until the page is left.
let memory = "[]";
const listeners = new Set<() => void>();
const read = () => {
  try {
    return window.sessionStorage.getItem(STORE) ?? memory;
  } catch {
    return memory;
  }
};
const write = (raw: string) => {
  memory = raw;
  try {
    window.sessionStorage.setItem(STORE, raw);
  } catch {
    // see above
  }
  listeners.forEach((l) => l());
};
const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => void listeners.delete(l);
};

export function TicketProvider({ children }: { children: ReactNode }) {
  const raw = useSyncExternalStore(subscribe, read, () => "[]");
  const legs = useMemo<TicketLeg[]>(() => {
    try {
      return JSON.parse(raw);
    } catch {
      return [];
    }
  }, [raw]);
  const setLegs = (next: TicketLeg[]) => write(JSON.stringify(next));
  const toggle = (leg: TicketLeg) => {
    if (legs.some((l) => l.marketTicker === leg.marketTicker && l.side === leg.side)) return setLegs(legs.filter((l) => l.marketTicker !== leg.marketTicker));
    setLegs([...legs.filter((l) => groupOf(l.marketTicker) !== groupOf(leg.marketTicker)), leg]);
  };
  return (
    <TicketContext.Provider value={{ legs, toggle }}>
      {children}
      <TicketPanel clear={() => setLegs([])} />
    </TicketContext.Provider>
  );
}

export function AddToTicket({ leg }: { leg: TicketLeg }) {
  const ctx = useContext(TicketContext);
  if (!ctx) return null;
  const on = ctx.legs.some((l) => l.marketTicker === leg.marketTicker && l.side === leg.side);
  return (
    <Button size="sm" variant={on ? "default" : "outline"} onClick={() => ctx.toggle(leg)} aria-pressed={on} title="Adds this game to a ticket: one bet that pays only if every game on it wins.">
      {on ? `On the ticket: ${leg.side}` : `Add “${leg.side}” at ${cents(leg.price)}`}
    </Button>
  );
}

function TicketPanel({ clear }: { clear: () => void }) {
  const ctx = useContext(TicketContext)!;
  const router = useRouter();
  const [contracts, setContracts] = useState("1");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { legs } = ctx;
  if (legs.length === 0) return null;
  const price = legs.reduce((a, l) => a * l.price, 1);
  const probability = legs.reduce((a, l) => a * l.probability, 1);
  const notFlagged = legs.filter((l) => l.flagged === false).length; // legs saved before this field existed are not counted
  const runs = legs.map((l) => l.runId);
  const linked = new Set(runs.filter((r) => runs.indexOf(r) !== runs.lastIndexOf(r))).size;

  async function prepare() {
    setError(null);
    setPending(true);
    try {
      const res = await fetch("/api/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Requested-With": "web" },
        body: JSON.stringify({ legs: legs.map((l) => ({ run_id: l.runId, market_ticker: l.marketTicker, side: l.side })), contracts: Number.parseInt(contracts, 10) || 0 }),
      });
      if (res.status === 201) {
        clear();
        return router.push("/approval");
      }
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
      <h2 className="text-lg font-semibold tracking-tight">Ticket: {legs.length} leg{legs.length === 1 ? "" : "s"}</h2>
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
        The ticket pays only if <strong>every</strong> leg wins. Together: price {cents(price)} each, our chance {pct(probability)}.
      </p>
      <p className="mt-1 text-sm text-muted-foreground">
        The price is the legs multiplied, as in the simulation. A real combo on Kalshi is quoted on request and is usually worse. Each leg adds the model’s error, so more legs means a less
        certain ticket.{legs.length >= 3 ? " Three or more legs: take extra care." : ""}
        {legs.length >= 15 ? ` This ticket wins about 1 time in ${Math.max(1, Math.round(1 / probability))}.` : ""}
      </p>
      {notFlagged > 0 ? (
        <p className="mt-1 text-sm text-warn">
          {notFlagged === 1 ? "One of these legs is" : `${notFlagged} of these legs are`} not marked worth a look: our estimate there is not better than the market’s price.
        </p>
      ) : null}
      {linked > 0 ? (
        <p className="mt-1 text-sm text-warn">
          {linked === 1 ? "One game has" : `${linked} games have`} several bets on this ticket. Those bets move together, so the combined chance and price here are rough, and a real Kalshi
          quote will differ in a way we cannot predict.
        </p>
      ) : null}
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
