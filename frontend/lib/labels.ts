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
  if (/more likely a model error/.test(reason)) return "the gap is so large that a model error is more likely than an opportunity";
  if (/no plain AI call/.test(reason)) return "there is no plain AI call to compare the research with";
  if (/did not move the forecast/.test(reason)) return "the research did not move our forecast toward the gap";
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
  total: "Total goals, runs or points",
  btts: "Both teams to score",
  spread: "Margin of victory",
};

export const ORDER_STATE: Record<string, string> = {
  proposed: "Waiting for approval",
  approved: "Approved, not placed yet",
  rejected: "Rejected",
  expired: "Expired",
  placed: "Placed in the simulation",
  simulated_rejected: "The simulation refused it",
  settled: "Game ended",
};

export const CHECK_NAME: Record<string, string> = {
  not_paused: "No stop rule has triggered (the simulated losses are below the limits)",
  not_expired: "Still within its time limit",
  game_not_started: "The game has not started",
  forecast_fresh: "The forecast is recent enough",
  within_limits: "Within the betting limits",
  legs_ok: "The legs are allowed (not too many, one per game)",
  price_ok: "The price has not moved against us",
  enough_contracts: "Enough contracts are offered at that price",
  still_worth_a_look: "Still worth a look at today’s prices",
};
