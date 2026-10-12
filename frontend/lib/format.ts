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
