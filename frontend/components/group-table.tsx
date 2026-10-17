import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { centsPrecise } from "@/lib/format";
import { KIND_HEADING } from "@/lib/labels";
import type { DashboardGroup, PaperStats } from "@/lib/types";
import { cn } from "@/lib/utils";

const MIN_BETS = 30; // below this a paper average is noise (the same rule as the cards)
const dollars = (x: number | null) => (x === null ? "–" : `${x < 0 ? "−" : x > 0 ? "+" : ""}$${Math.abs(x).toFixed(2)}`);
const score = (x: number | null) => (x === null ? "–" : x.toFixed(3));
const name = (g: DashboardGroup) => g.sport ?? (g.kind ? (KIND_HEADING[g.kind] ?? g.kind) : "");
const tone = (x: number | null) => (x === null ? "" : x > 0 ? "text-good" : x < 0 ? "text-destructive" : "");

function PaperCell({ p }: { p: PaperStats }) {
  return p.bets === 0 ? (
    <span className="text-muted-foreground">none</span>
  ) : (
    <>
      <span className={cn("font-medium", tone(p.average_result))}>{centsPrecise(p.average_result)}</span>
      {p.bets < MIN_BETS ? <span className="block text-xs text-muted-foreground">too few to read</span> : null}
    </>
  );
}

/** A table of results by group (a sport, or a kind of market). Two column sets: the accuracy of the forecasts, or the simulated result. */
export function GroupTable({ title, id, rows, mode, firstColumn }: { title: string; id: string; rows: DashboardGroup[]; mode: "accuracy" | "profit"; firstColumn: string }) {
  return (
    <section className="min-w-0 rounded-xl border bg-card p-5" aria-labelledby={id}>
      <h2 id={id} className="mb-3 text-lg font-semibold">
        {title}
      </h2>
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">No finished games yet.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{firstColumn}</TableHead>
              {mode === "accuracy" ? (
                <>
                  <TableHead className="text-right">Games</TableHead>
                  <TableHead className="text-right">Ours</TableHead>
                  <TableHead className="text-right">Plain AI</TableHead>
                  <TableHead className="text-right">Kalshi</TableHead>
                  <TableHead>Ours against Kalshi</TableHead>
                </>
              ) : (
                <>
                  <TableHead className="text-right">Bets</TableHead>
                  <TableHead className="text-right">Won</TableHead>
                  <TableHead>Average per contract</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead>Flagged bets</TableHead>
                </>
              )}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((g) => (
              <TableRow key={name(g)}>
                <TableCell className="whitespace-normal font-medium">{name(g)}</TableCell>
                {mode === "accuracy" ? (
                  <>
                    <TableCell className="text-right tabular-nums">{g.games}</TableCell>
                    <TableCell className="text-right tabular-nums">{score(g.ours)}</TableCell>
                    <TableCell className="text-right tabular-nums">{score(g.baseline)}</TableCell>
                    <TableCell className="text-right tabular-nums">{score(g.market)}</TableCell>
                    <TableCell className="whitespace-normal text-sm">
                      {g.too_few || g.ours === null || g.market === null
                        ? <span className="text-muted-foreground">too few games to read</span>
                        : g.ours < g.market
                          ? `✓ ahead by ${(g.market - g.ours).toFixed(3)}`
                          : `behind by ${(g.ours - g.market).toFixed(3)}`}
                    </TableCell>
                  </>
                ) : (
                  <>
                    <TableCell className="text-right tabular-nums">{g.paper.bets}</TableCell>
                    <TableCell className="text-right tabular-nums">{g.paper.won}</TableCell>
                    <TableCell className="whitespace-normal tabular-nums">
                      <PaperCell p={g.paper} />
                    </TableCell>
                    <TableCell className={cn("text-right tabular-nums", tone(g.paper.total_result))}>{dollars(g.paper.total_result)}</TableCell>
                    <TableCell className="whitespace-normal tabular-nums text-sm">
                      {g.flagged.bets === 0 ? (
                        <span className="text-muted-foreground">none</span>
                      ) : (
                        <>
                          {g.flagged.won} of {g.flagged.bets} won, <span className={tone(g.flagged.average_result)}>{centsPrecise(g.flagged.average_result)}</span>
                          {g.flagged.bets < MIN_BETS ? <span className="block text-xs text-muted-foreground">too few to read</span> : null}
                        </>
                      )}
                    </TableCell>
                  </>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </section>
  );
}
