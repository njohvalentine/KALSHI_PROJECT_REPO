"use client";

import { useSyncExternalStore } from "react";

const utc = (d: Date) =>
  d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "UTC" }) + " UTC";

const local = (d: Date) =>
  d.toLocaleString("en-US", { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

const subscribe = () => () => {};

/** A time in the viewer's own time zone. The server cannot know it, so the browser fills it in after
 * the page loads; until then (and without scripts) the time is shown in UTC. */
export function LocalTime({ iso }: { iso: string | null }) {
  const date = iso ? new Date(iso) : null;
  const valid = date !== null && !Number.isNaN(date.getTime());
  const text = useSyncExternalStore(
    subscribe,
    () => (valid && date ? local(date) : null), // in the browser
    () => null, // on the server
  );
  if (!valid || !date) return <span>–</span>;
  return <time dateTime={iso ?? undefined}>{text ?? utc(date)}</time>;
}
