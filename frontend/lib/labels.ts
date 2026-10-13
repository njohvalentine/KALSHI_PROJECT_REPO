import type { ComparisonOutcome, Finding, Verdict } from "@/lib/types";

/** Plain-English names for what the backend calls things, so the page never shows internal words. */
export const FRAMING: Record<string, string> = {
  evidence_first: "Looked at each fact first",
  base_rate_first: "Started from how often such sides win",
  devils_advocate: "Argued against its first view",
};

export const VERDICT: Record<Verdict, string> = {
  supported: "Supported by the page",
  not_supported: "The page says something different",
  could_not_check: "Could not check",
};

export const STAGES = [
  { key: "research", label: "Research" },
  { key: "fetch", label: "Read the cited pages" },
  { key: "check", label: "Check the claims" },
  { key: "forecast", label: "Forecast" },
  { key: "compare", label: "Compare with the market" },
];

export const COST_LABEL: Record<string, string> = {
  research: "Research",
  check: "Checking claims",
  forecast: "Forecasters",
  baseline: "Plain AI call",
};

export function fetchLabel(status: string, detail: string | null): string {
  switch (status) {
    case "ok":
      return "Read";
    case "blocked":
      return "Not allowed to fetch";
    case "empty_js":
      return "Needs JavaScript or has almost no text";
    case "unsupported":
      return "Not a web page we can read";
    case "too_large":
      return "Too large";
    case "failed":
      return `Could not read${detail ? ` (${detail.replace(/^the site answered /, "")})` : ""}`;
    default:
      return "Not fetched";
  }
}

/** The backend's reasons for not flagging a gap, in plain words. */
export function plainReason(reason: string): string {
  if (/below EDGE_MIN/.test(reason)) return "the gap after fees is small";
  if (/least favourable forecaster/.test(reason)) return "the least favourable forecaster sees no gap";
  if (/no supported evidence/.test(reason)) return "no claim was supported by its page";
  const claims = reason.match(/only (\d+) supported claims/);
  if (claims) return `only ${claims[1]} supported claims`;
  if (/contracts at the best price/.test(reason)) return "too few contracts offered at that price";
  if (/no executable price/.test(reason)) return "no price to compare with";
  if (/no market/.test(reason)) return "no market price was available";
  return reason;
}

/** Findings about odds are market information; the forecasters never receive them. */
export function isMarketFinding(f: Finding): boolean {
  return f.kind === "market_odds" || /odds/i.test(f.angle);
}

export function sideText(o: ComparisonOutcome): string {
  if (o.side === "yes") return `buying “yes” at ${Math.round((o.yes_ask ?? 0) * 100)}¢`;
  if (o.side === "no") return `buying “no” at ${Math.round((o.no_ask ?? 0) * 100)}¢`;
  return "";
}

export const KIND_HEADING: Record<string, string> = {
  winner: "Who wins",
  total: "Total goals or runs",
  btts: "Both teams to score",
  spread: "Margin of victory",
};
