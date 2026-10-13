export function dateTime(iso: string | null): string {
  const date = iso ? new Date(iso) : null;
  return date && !Number.isNaN(date.getTime())
    ? date.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
    : "–";
}

export function duration(start: string | null, end: string | null): string {
  if (!start || !end) return "–";
  const seconds = Math.round((new Date(end).getTime() - new Date(start).getTime()) / 1000);
  if (!Number.isFinite(seconds) || seconds < 0) return "–";
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

export function money(cost: string | null): string {
  if (cost === null) return "unknown";
  const value = Number.parseFloat(cost);
  return Number.isFinite(value) ? `$${value.toFixed(value < 0.1 ? 3 : 2)}` : "unknown";
}

export function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** "43–44¢" from Kalshi's dollar strings: the price one can sell at and the price one can buy at. */
export function bidAsk(bid: string | null, ask: string | null): string {
  const b = Number.parseFloat(bid ?? "");
  const a = Number.parseFloat(ask ?? "");
  if (!Number.isFinite(b) || !Number.isFinite(a)) return "–";
  return `${Math.round(b * 100)}–${Math.round(a * 100)}¢`;
}

/** 0.57 -> "57%". */
export function pct(probability: number): string {
  return `${Math.round(probability * 100)}%`;
}

/** A price in dollars (0.42) as cents: "42¢". */
export function cents(dollars: number | null): string {
  return dollars === null || !Number.isFinite(dollars) ? "–" : `${Math.round(dollars * 100)}¢`;
}

/** A gap in dollars per contract (0.2188) as "+22¢". */
export function gapCents(dollars: number | null): string {
  if (dollars === null || !Number.isFinite(dollars)) return "–";
  const value = Math.round(dollars * 100);
  return `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value)}¢`;
}

/** "5 min ago", "2 h ago", "3 days ago". */
export function ago(iso: string | null, now: number = Date.now()): string {
  const time = iso ? new Date(iso).getTime() : Number.NaN;
  if (!Number.isFinite(time)) return "";
  const minutes = Math.max(0, Math.round((now - time) / 60000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}
