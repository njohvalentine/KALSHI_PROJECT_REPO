export type Source = { url: string; title?: string };
export type Claim = { text: string; kind: "sourced" | "uncited" | "none"; sources: Source[] };
export type Finding = { angle: string; question: string; claims: Claim[]; ignored_citations?: number };
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
};

export type Run = RunSummary & {
  plan: { angles: { name: string; question: string }[]; cut_angles: number } | null;
  result: { findings: Finding[]; errors: RunError[] } | null;
};

export const isActive = (status: RunSummary["status"]) => status === "queued" || status === "running";
