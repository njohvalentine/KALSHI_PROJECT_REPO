export type Source = { url: string; title?: string };
export type Claim = { text: string; kind: "sourced" | "uncited" | "none"; sources: Source[] };
export type Finding = { angle: string; question: string; kind?: "evidence" | "market_odds"; claims: Claim[]; ignored_citations?: number };
export type RunError = { angle: string; error: string };

export type RunSummary = {
  id: string;
  event_ticker: string;
  event_title: string;
  status: "queued" | "running" | "done" | "failed";
  error: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  input_tokens: number;
  output_tokens: number;
  search_calls: number;
  cost_usd: string | null;
  cost_note: string | null;
  over_budget: boolean;
  sourced_claims: number;
  stage: string | null;
  flagged_outcomes: number | null;
};

export type Verdict = "supported" | "not_supported" | "could_not_check";
export type ClaimCheck = { finding_index: number; claim_index: number; source_url: string; verdict: Verdict; reason: string };
export type PageInfo = {
  url: string;
  title: string | null;
  fetch_status: string;
  fetch_detail: string | null;
  fetch_method: string | null;
  http_status: number | null;
  fetched_at: string | null;
};
export type ForecastRow = {
  forecaster_index: number;
  variant: string;
  market_ticker: string;
  probability: number;
  reasoning: string;
  model: string;
};
export type MarketKind = "winner" | "total" | "btts" | "spread";
export type PredictionOutcome = {
  market_ticker: string;
  kind?: MarketKind;
  outcome: string;
  probability: number;
  min: number;
  max: number;
  spread: number;
  forecasts: { variant: string; probability: number }[];
};
export type ComparisonOutcome = {
  market_ticker: string;
  yes_bid: number | null;
  yes_ask: number | null;
  no_ask: number | null;
  side: "yes" | "no" | null;
  net_edge: number | null;
  worst_case_edge: number | null;
  baseline?: number | null;
  research_shift?: number | null;
  meaningful: boolean;
  reasons: string[];
};
export type Comparison = {
  unavailable?: string;
  priced_at?: string;
  fee?: { fee_type: string; multiplier: number; source: string };
  outcomes?: ComparisonOutcome[];
};
export type Prediction = {
  unavailable?: string;
  outcomes?: PredictionOutcome[];
  forecasters_valid?: number;
  dropped?: { index: number; variant: string; reason: string }[];
  evidence?: "supported" | "none";
  supported_claims?: number;
  markets_not_offered?: string[];
  adjustments?: { forecaster: number; note: string }[];
  comparison?: Comparison;
};

export type Run = RunSummary & {
  plan: { angles: { name: string; question: string }[]; cut_angles: number } | null;
  result: { findings: Finding[]; errors: RunError[]; costs?: Record<string, string | null> } | null;
  prediction: Prediction | null;
  sport?: string | null;
  measured?: boolean | null;
  pages: PageInfo[];
  claim_checks: ClaimCheck[];
  forecasts: ForecastRow[];
  baseline: Record<string, number> | null;
  costs: Record<string, string | null> | null;
};

/** What the Games list needs from the latest finished run of a game. */
export type LatestForecast = {
  forecast_at: string | null;
  outcomes: { market_ticker: string; probability: number; flagged: boolean }[];
};
export type LatestRun = { event_ticker: string; id: string; status: RunSummary["status"]; forecast: LatestForecast | null };

export const isActive = (status: RunSummary["status"]) => status === "queued" || status === "running";

export type Outcome = {
  market_ticker: string;
  label: string;
  bid: string | null;
  ask: string | null;
  last: string | null;
  volume: string | null;
  status: string | null;
};

export type Game = {
  event_ticker: string;
  title: string;
  sub_title: string | null;
  sport: string;
  league: string;
  starts_at: string | null;
  closes_at: string | null;
  started: boolean;
  measured: boolean; // false: the sport has fewer scored games than measured_min_games
  scored_games: number;
  outcomes: Outcome[];
};

export type GamesResponse = {
  games: Game[];
  total: number;
  hidden_started: number;
  sports: string[];
  errors: { series: string; league: string; error: string }[];
  notes: string[];
  more_sports: { sport: string; games: number; series: number; also_measured: boolean }[];
  measured_min_games: number;
  fetched_at: string;
};

export type OpportunityBest = {
  market_ticker: string;
  kind: string;
  market: string;
  side: "yes" | "no";
  price: number;
  our_probability: number;
  market_probability: number;
  gap: number;
  spread: number;
  reasons: string[];
  fee_source: string | null;
};
export type Opportunity = {
  run_id: string;
  event_ticker: string;
  title: string;
  starts_at: string | null;
  forecast_at: string | null;
  age_hours: number | null;
  stale: boolean;
  supported_claims: number;
  evidence: string | null;
  flagged: boolean;
  flagged_markets: number;
  sport: string | null;
  league: string | null;
  measured: boolean | null; // false: no scored results for this sport yet; null: sport unknown
  best: OpportunityBest | null;
  unavailable: string | null;
  risks: string[];
};
export type OpportunitiesResponse = {
  opportunities: Opportunity[];
  games_considered: number;
  flagged_games: number;
  top_reasons: { reason: string; games: number }[];
  generated_at: string;
  max_age_hours: number;
  max_ticket_legs: number;
};

export type AlertItem = {
  id: number;
  created_at: string;
  kind: string;
  event_ticker: string;
  run_id: string | null;
  title: string;
  text: string;
  status: "recorded" | "sent" | "failed" | "held_back";
  detail: string | null;
};
export type AlertsResponse = {
  alerts: AlertItem[];
  monitor: {
    enabled: boolean;
    interval_minutes: number;
    channel: string;
    last_cycle_at: string | null;
    last_error: string | null;
    auto_research_cap: number;
    auto_research_started_today: number;
  };
};

export type OrderCheck = { name: string; leg: number | null; ok: boolean; blocking: boolean; detail: string };
export type OrderLegInfo = {
  position: number;
  run_id: string;
  event_ticker: string;
  market_ticker: string;
  outcome: string;
  title: string;
  game_start: string | null;
  side: "yes" | "no";
  price: number;
  our_probability: number;
  fill_price: number | null;
  won: boolean | null;
};
export type OrderState = "proposed" | "approved" | "rejected" | "expired" | "placed" | "simulated_rejected" | "settled";
export type SimOrder = {
  id: number;
  run_id: string;
  event_ticker: string;
  market_ticker: string;
  outcome: string;
  title: string;
  game_start: string | null;
  side: "yes" | "no";
  price: number;
  contracts: number;
  max_cost: number;
  fee_estimate: number;
  our_probability: number;
  gap: number;
  forecast_at: string | null;
  state: OrderState;
  created_at: string;
  expires_at: string;
  approved_at: string | null;
  reason: string | null;
  placed_at: string | null;
  fill_contracts: number | null;
  fill_price: number | null;
  fill_fee: number | null;
  settled_at: string | null;
  won: boolean | null;
  paper_result: number | null;
  legs: OrderLegInfo[];
  checks?: OrderCheck[];
};
export type OrdersResponse = { orders: SimOrder[]; totals: { settled: number; won: number; paper_result: number } };

export type DashboardGroup = { sport: string; games: number; ours: number | null; baseline: number | null; market: number | null; too_few: boolean };
export type DashboardResponse = {
  games: number;
  outcomes: number;
  unresolved: number;
  games_needed: number;
  message: { kind: "too_few" | "ahead" | "no_edge"; text: string };
  scores: { n: number; ours: number | null; baseline: number | null; market: number | null };
  by_sport: DashboardGroup[];
  flagged: { bets: number; won: number; average_result: number | null; total_result: number | null; too_few: boolean };
  spend: { total_usd: number; runs: number; note: string };
};
