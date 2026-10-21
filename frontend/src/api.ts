export type Metrics = {
  total: number;
  completed: number;
  failed: number;
  canceled: number;
  pending: number;
  running: number;
  average_score: number | null;
  pass_rate: number;
  coverage: number;
  error_rate: number;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number;
  retries: number;
};
export type Config = {
  dataset_version_id: string;
  prompt_version_id: string;
  provider: string;
  model: string;
  temperature: number;
  evaluators: string[];
  concurrency: number;
  max_attempts: number;
  timeout_seconds: number;
  pass_threshold: number;
  judge_model: string;
  embedding_model: string;
  retrieval_k: number;
  input_cost_per_million: number;
  output_cost_per_million: number;
  capture_content: boolean;
  mock_latency_ms: number;
  prompt_name?: string;
  evaluator_versions?: Record<string, string>;
};
export type Run = {
  id: string;
  name: string;
  status: string;
  total: number;
  config: Config;
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
  metrics: Metrics;
  dataset_version_id: string;
  usage?: UsageSummary;
};
export type Version = {
  id: string;
  number: number;
  fingerprint: string;
  case_count: number;
  created_at: number;
};
export type Dataset = {
  id: string;
  name: string;
  description: string;
  created_at: number;
  versions: Version[];
};
export type Prompt = {
  id: string;
  name: string;
  template: string;
  created_at: number;
};
export type Experiment = {
  id: string;
  name: string;
  config: Config;
  created_at: number;
};
export type Case = {
  case_id: string;
  input: string;
  reference_answer: string;
  reference_contexts: string[];
  relevant_document_ids: string[];
  retrieved_document_ids: string[];
  tags: string[];
};
export type Span = {
  name: string;
  span_id: string;
  parent_span_id: string | null;
  started_at: number;
  ended_at: number;
  duration_ms: number;
  status: string;
  error?: string;
  attributes: Record<string, string | number>;
};
export type Score = {
  evaluator: string;
  version: string;
  value: number;
  reason: string;
  details: Record<string, number>;
};
export type Result = {
  id: string;
  run_id: string;
  case_id: string;
  status: string;
  score: number | null;
  passed: boolean | null;
  error: string | null;
  latency_ms: number | null;
  input_tokens: number;
  output_tokens: number;
  cost: number;
  attempts: number;
  trace_id: string | null;
  output: string | null;
  scores: Score[];
  case?: Case;
  spans?: Span[];
  human_score: number | null;
  human_note: string | null;
  attempt_history?: {
    number: number;
    status: string;
    error: string | null;
    trace_id: string | null;
    trace_complete: boolean;
  }[];
};
export type Trace = {
  trace_id: string;
  case_id: string;
  run_id: string | null;
  result_id: string | null;
  status: string;
  latency_ms: number | null;
  error: string | null;
  span_count: number;
  created_at: number;
  source: string;
  attempt?: number;
};
export type Comparison = {
  baseline: Run;
  candidate: Run;
  paired_cases: number;
  cost_comparison_complete?: boolean;
  mean_score_delta: number | null;
  score_delta_95_ci: [number, number] | null;
  uncertainty_method: string;
  counts: Record<string, number>;
  cases: {
    case_id: string;
    baseline_score: number | null;
    candidate_score: number | null;
    delta: number | null;
    change: string;
    candidate_result_id: string;
  }[];
};
export type Thresholds = {
  minimum_pass_rate: number;
  maximum_pass_rate_drop: number;
  maximum_p95_latency_ms: number;
  maximum_error_rate: number;
  minimum_coverage: number;
  minimum_paired_cases: number;
};
export const defaultThresholds: Thresholds = {
  minimum_pass_rate: 0.9,
  maximum_pass_rate_drop: 0.03,
  maximum_p95_latency_ms: 2500,
  maximum_error_rate: 0.02,
  minimum_coverage: 0.95,
  minimum_paired_cases: 5,
};
export type Gate = {
  id: string;
  decision: string;
  checks: {
    name: string;
    actual: number | null;
    limit: number;
    passed: boolean;
  }[];
  insufficient_reasons: string[];
  comparison: Comparison;
  thresholds: Thresholds;
};
export type Report = {
  id: string;
  created_at: number;
  decision: string;
  report: Gate;
};
export type Overview = {
  metrics: Metrics;
  run_count: number;
  dataset_count: number;
  active_runs: number;
  runs: Run[];
  error_categories: Record<string, number>;
  usage?: UsageSummary;
};
export type Workspace = {
  project: { id: string; name: string };
  mode: string;
  provider_configured: boolean;
  auth_enabled: boolean;
  auth_mode?: string;
  role?: string;
  user?: { id: string; name: string; is_admin: boolean };
  credential_encryption?: boolean;
};

export type UsageSummary = {
  calls: number;
  known_cost: number;
  uncertain_calls: number;
  unpriced_calls: number;
  legacy_results: number;
  complete: boolean;
  note: string;
};

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const token = sessionStorage.getItem("evalscope-token");
  const project = sessionStorage.getItem("evalscope-project");
  const response = await fetch("/api/v1" + path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(project ? { "X-Project-ID": project } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const body = await response
      .json()
      .catch(() => ({ detail: "The server could not complete the request." }));
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : Array.isArray(body.detail)
          ? body.detail
              .map(
                (e: { loc: string[]; msg: string }) =>
                  `${e.loc.slice(1).join(".")}: ${e.msg}`,
              )
              .join("; ")
          : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return response.json();
}
export const post = <T>(path: string, data: unknown) =>
  api<T>(path, { method: "POST", body: JSON.stringify(data) });
export const pct = (n: number | null | undefined, digits = 1) =>
  n == null ? "—" : `${(n * 100).toFixed(digits)}%`;
export const ms = (n: number | null | undefined) =>
  n == null
    ? "—"
    : n >= 1000
      ? `${(n / 1000).toFixed(2)}s`
      : `${Math.round(n)}ms`;
export const date = (n: number) =>
  new Date(n * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
export const money = (n: number) => `$${n.toFixed(n > 0 && n < 0.01 ? 5 : 2)}`;
export const terminal = (s: string) =>
  ["COMPLETED", "PARTIAL", "FAILED", "CANCELED"].includes(s);
