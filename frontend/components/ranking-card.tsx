import Link from "next/link";
import { Confidence } from "@/components/confidence";
import { LocalTime } from "@/components/local-time";
import { backendFetch } from "@/lib/backend";
import { cents, gapCents, pct } from "@/lib/format";
import type { RankingResponse } from "@/lib/types";

/** The five likeliest outcomes of the researched games that have not started, with the Kalshi price and the gap beside each. The full list is on the Ranking page. */
export async function RankingCard() {
  const res = await backendFetch("/api/ranking?limit=5&kind=winner");
  if (!res.ok) {
    return (
      <section className="mt-4 rounded-xl border bg-card p-5" aria-labelledby="rank-heading">
        <h2 id="rank-heading" className="text-lg font-semibold">Most probable results</h2>
        <p className="text-sm text-muted-foreground">Could not be read; open the Ranking page.</p>
      </section>
    );
  }
  const d = (await res.json()) as RankingResponse;
  return (
    <section className="mt-4 rounded-xl border bg-card p-5" aria-labelledby="rank-heading">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="rank-heading" className="text-lg font-semibold">Most probable results</h2>
        <Link href="/ranking" className="text-sm text-primary underline underline-offset-4">
          See the full ranking
        </Link>
      </div>
      {d.rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nothing yet: no researched game that has not started with a result priced under 90¢. Research a game on the Games page.</p>
      ) : (
        <>
          <p className="mb-3 text-sm text-muted-foreground">
            The five likeliest match results among {d.games_considered} researched game{d.games_considered === 1 ? "" : "s"} that have not started, with the Kalshi price beside each. Likely is not the same as good value: look at the gap. The full ranking has every market.
          </p>
          <ul className="grid gap-3">
            {d.rows.map((o) => (
              <li key={o.market_ticker} className="grid gap-x-4 gap-y-1 border-b pb-3 last:border-b-0 last:pb-0 sm:grid-cols-[1fr_auto]">
                <div className="min-w-0">
                  <Link href={`/prediction/${o.run_id}`} className="font-medium text-primary underline-offset-4 hover:underline">
                    {o.market}
                  </Link>
                  <div className="text-sm text-muted-foreground">
                    {o.title} · starts <LocalTime iso={o.starts_at} />
                  </div>
                  <Confidence level={o.confidence.level} reasons={o.confidence.reasons} />
                </div>
                <div className="text-right tabular-nums">
                  <div className="text-lg font-semibold">{pct(o.our_probability)}</div>
                  <div className="text-sm text-muted-foreground">
                    Kalshi {cents(o.price)} · gap {gapCents(o.gap)}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
