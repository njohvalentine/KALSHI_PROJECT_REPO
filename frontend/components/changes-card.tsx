import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { backendFetch } from "@/lib/backend";
import { ago } from "@/lib/format";
import { ALERT_KIND } from "@/lib/labels";
import type { AlertsResponse } from "@/lib/types";

const brief = (text: string) => text.split(/(?<=[.!?])\s/).slice(0, 2).join(" "); // the first two sentences: the title alone says too little

/** What changed lately: the watcher's last alerts (price moves, new forecasts, updates due, flagged and no longer flagged). The full list is on the Opportunities page. */
export async function ChangesCard() {
  const res = await backendFetch("/api/alerts?limit=6");
  if (!res.ok) return null;
  const { alerts, monitor } = (await res.json()) as AlertsResponse;
  return (
    <section className="mt-4 rounded-xl border bg-card p-5" aria-labelledby="changes-heading">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="changes-heading" className="text-lg font-semibold">What changed</h2>
        <Link href="/opportunities" className="text-sm text-primary underline underline-offset-4">
          All alerts
        </Link>
      </div>
      {!monitor.enabled ? (
        <p className="text-sm text-muted-foreground">The watcher is off, so nothing is tracked. It is switched on with MONITOR_ENABLED=true.</p>
      ) : alerts.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Nothing yet. The watcher looks every {monitor.interval_minutes} minutes and says here when a price moves, a new forecast differs, or a game is due its lineup update.
        </p>
      ) : (
        <ul className="grid gap-3">
          {alerts.map((a) => (
            <li key={a.id} className="border-b pb-3 text-sm last:border-b-0 last:pb-0">
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <Badge variant="outline">{ALERT_KIND[a.kind] ?? a.kind}</Badge>
                <span className="text-muted-foreground">{ago(a.created_at)}</span>
                {a.run_id ? (
                  <Link href={`/prediction/${a.run_id}`} className="font-medium text-primary underline-offset-4 hover:underline">
                    {a.title}
                  </Link>
                ) : (
                  <span className="font-medium">{a.title}</span>
                )}
              </div>
              <p className="text-muted-foreground">{brief(a.text)}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
