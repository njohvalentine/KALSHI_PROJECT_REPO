"use client";

import { createContext, useContext, useState } from "react";
import { Button } from "@/components/ui/button";
import { TableCell, TableHead } from "@/components/ui/table";
import type { ScreenResponse, ScreenResult } from "@/lib/types";

/** The free bookmaker check on the Games page. It is a button that sends a POST (it spends odds credits and saves rows), never a link:
 * the labels live here, in the page, and a reload forgets them (pressing again inside the 10-minute cache costs nothing). */
type Screen = { screen: ScreenResponse | null; failed: boolean; pending: boolean; run: () => void };
const Ctx = createContext<Screen>({ screen: null, failed: false, pending: false, run: () => {} });

export function ScreenProvider({ query, children }: { query: string; children: React.ReactNode }) {
  const [screen, setScreen] = useState<ScreenResponse | null>(null);
  const [failed, setFailed] = useState(false);
  const [pending, setPending] = useState(false);

  async function run() {
    setPending(true);
    setFailed(false);
    try {
      const res = await fetch(`/api/games/screen?${query}`, { method: "POST", headers: { "X-Requested-With": "web" } });
      if (!res.ok) throw new Error(String(res.status));
      setScreen((await res.json()) as ScreenResponse);
    } catch {
      setFailed(true);
    } finally {
      setPending(false);
    }
  }

  return <Ctx.Provider value={{ screen, failed, pending, run }}>{children}</Ctx.Provider>;
}

export function ScreenBar({ maxLeagues }: { maxLeagues: number }) {
  const { screen, failed, pending, run } = useContext(Ctx);
  const credits = screen?.credits;
  return (
    <div className="mb-4 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" variant="outline" onClick={run} disabled={pending}>
          {pending ? "Checking…" : screen ? "Check again" : "Check these games against the bookmakers"}
        </Button>
        <span className="text-muted-foreground">
          {failed
            ? "The check could not be made. Press the button to try again."
            : screen
              ? `Checked against the bookmakers${credits && credits.used !== null ? `: ${credits.used} odds credit${credits.used === 1 ? "" : "s"} used` : ""}${
                  credits && credits.remaining !== null ? `, ${credits.remaining} left this month` : ""
                }. No OpenAI credit was used. It is a guide for choosing what to research, not a recommendation.`
              : `To see which games are worth researching. It reads the bookmakers’ prices (at most ${maxLeagues} odds credits, one per league) and uses no OpenAI credit.`}
        </span>
      </div>
      {screen?.notes.map((n) => (
        <p key={n} className="mt-1 text-warn">
          {n}
        </p>
      ))}
    </div>
  );
}

function Label({ result }: { result: ScreenResult | undefined }) {
  if (!result) return <span className="text-muted-foreground">Not checked (started, or too far ahead)</span>;
  return <span className={result.status === "promising" ? "font-medium text-good" : "text-muted-foreground"}>{result.text}</span>;
}

export function ScreenHead() {
  const { screen } = useContext(Ctx);
  return screen ? <TableHead className="hidden px-4 py-3 lg:table-cell">Bookmakers</TableHead> : null;
}

export function ScreenCell({ ticker }: { ticker: string }) {
  const { screen } = useContext(Ctx);
  return screen ? (
    <TableCell className="hidden max-w-[34ch] whitespace-normal px-4 py-3.5 text-sm lg:table-cell">
      <Label result={screen.results[ticker]} />
    </TableCell>
  ) : null;
}

export function ScreenMobile({ ticker }: { ticker: string }) {
  const { screen } = useContext(Ctx);
  return screen && screen.results[ticker] ? (
    <div className="mt-2 text-sm lg:hidden">
      <Label result={screen.results[ticker]} />
    </div>
  ) : null;
}
