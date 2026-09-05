import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type Project = components["schemas"]["ProjectResponse"];
export type ProjectCreate = components["schemas"]["ProjectCreateRequest"];
export type DefinitionCreate = components["schemas"]["DefinitionCreateRequest"];
export type CoverageResponse = components["schemas"]["CoverageResponse"];
export type CorporateActionResponse = components["schemas"]["CorporateActionResponse"];
export type DailyBarResponse = components["schemas"]["DailyBarResponse"];
export type FundamentalFactResponse = components["schemas"]["FundamentalFactResponse"];
export type SecurityListSummary = components["schemas"]["SecurityListSummaryResponse"];
export type CompositeDownloadRequest = AnySchema;
export type CompositeDownloadResponse = AnySchema;
export type ProviderDownloadItem = AnySchema;
export type ProviderDownloadRequest = AnySchema;
export type ProviderDownloadResponse = AnySchema;

export type DownloadEventResponse = components["schemas"]["DownloadEventResponse"];
export type DownloadSnapshotResponse = components["schemas"]["DownloadSnapshotResponse"];
export type DownloadStartResponse = components["schemas"]["DownloadStartResponse"];

export type Security = components["schemas"]["SecurityResponse"];
export type SecuritySummary = components["schemas"]["SecuritySummaryResponse"];
export type Watchlist = components["schemas"]["WatchlistResponse"];
export type WatchlistItem = components["schemas"]["WatchlistItemResponse"];
type AnySchema = any;

export type ResearchThesis = AnySchema;
export type ComparableValuation = AnySchema;
export type SavedValuation = AnySchema;
export type FCFFDCFRequest = AnySchema;
export type FCFFDCFSeed = AnySchema;
export type FCFFDCFValuation = AnySchema;
export type CashFlowForecastYear = AnySchema;
export type ScenarioResult = AnySchema;
export type SensitivityMatrix = AnySchema;
export type ValuationComparison = AnySchema;
export type ValuationComparisonItem = AnySchema;

export type IndicatorMetadata = components["schemas"]["IndicatorMetadataResponse"];
export type IndicatorParameter = components["schemas"]["IndicatorParameterResponse"];
export type IndicatorPoint = components["schemas"]["IndicatorPointResponse"];
export type IndicatorSeries = components["schemas"]["IndicatorSeriesResponse"];
export type IndicatorCalculateRequest = components["schemas"]["IndicatorCalculateRequest"];

export type PredictiveModelMetadata = AnySchema;
export type PredictiveModelParameter = AnySchema;
export type PredictiveModelRunRequest = AnySchema;
export type PredictiveModelRun = AnySchema;

export type StrategyMetadata = components["schemas"]["StrategyMetadataResponse"];
export type StrategyParameter = components["schemas"]["StrategyParameterResponse"];
export type StrategyTarget = components["schemas"]["StrategyTargetResponse"];
export type StrategyEvaluation = components["schemas"]["StrategyEvaluationResponse"];
export type SavedStrategyEvaluation = components["schemas"]["SavedStrategyEvaluationResponse"];
export type StrategyEvaluateRequest = components["schemas"]["StrategyEvaluateRequest"];
export type RunSummary = components["schemas"]["RunSummaryResponse"];

export type StrategyVerdictRequest = components["schemas"]["StrategyVerdictRequest"];
export type StrategyVerdictResponse = components["schemas"]["StrategyVerdictResponse"];
export type GateResult = components["schemas"]["GateResultResponse"];
export type PartitionMetrics = components["schemas"]["PartitionMetricsResponse"];
export type VerdictEquityPoint = components["schemas"]["VerdictEquityPointResponse"];
export type FrictionTier = components["schemas"]["FrictionTierResponse"];

export interface OptionsGreeks {
  delta: number;
  theta: number;
  gamma: number;
  vega: number;
  implied_volatility: number;
}

export interface OptionsCandle {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface OptionsTrajectoryPoint {
  minute: string;
  underlying_price: number;
  spread_worst: number;
  spread_best: number;
  stop_level: number;
  delta?: number;
  stock_price?: number;
}

export interface OptionsSpreadPosition {
  id: string;
  security_id: string;
  spread_type: string;
  short_strike: number;
  long_strike: number;
  width: number;
  expiration: string;
  entry_credit: number;
  margin_required: number;
  full_possible_loss: number;
  return_on_margin_pct: number;
  annualized_rom_pct: number;
  worst_net_pnl: number;
  best_net_pnl: number;
  days_held: number;
  open_timestamp: string;
  open_rule: string;
  close_timestamp: string | null;
  close_rule: string;
  status: string;
  short_delta: number;
  implied_volatility: number;
  bid_ask_spread_drag: number;
  slippage_cost: number;
  execution_mode: string;
  reliability_pct: number;
  missing_minutes_count: number;
  stop_movements: Array<{ timestamp: string; underlying_price: number; new_stop: number; trigger_rule: string }>;
  greeks: Record<string, OptionsGreeks | null>;
  counterfactual: {
    outcome: string;
    avoided_loss_or_missed_gain: number;
    explanation: string;
  } | null;
  candles: OptionsCandle[];
  trajectory_points: OptionsTrajectoryPoint[];
  quantity: number;
  entry_fee: number;
  exit_fee: number;
}

export interface OptionsBacktestRequest {
  dataset_version_id: string;
  daily_dataset_version_id?: string | null;
  strategy_name?: string;
  strategy_revision?: string;
  symbol?: string | null;
  symbols?: string[] | null;
  watchlist?: string[] | null;
  start_date: string;
  end_date: string;
  starting_cash?: number;
  path?: "worst" | "best";
  automatic_selection?: boolean | null;
  fixed_short_contract_id?: string | null;
  fixed_long_contract_id?: string | null;
  dte_min?: number;
  dte_max?: number;
  delta_min?: number;
  delta_max?: number;
  target_delta?: number;
  iv_min?: number;
  iv_max?: number;
  previous_day_volume_min?: number;
  preferred_width?: number;
  fallback_width?: number;
  risk_per_position?: number;
  max_open_risk?: number;
  max_open_securities?: number;
  similarity_limit?: number;
  fee_per_leg?: number;
  risk_free_rate?: number;
  dividend_yield?: number;
  cash_interest_rate?: number;
}

export interface OptionsBacktestSpecification extends OptionsBacktestRequest {
  strategy_name: string;
  strategy_revision: string;
  dataset_version_id: string;
  start_date: string;
  end_date: string;
  starting_cash: number;
  path: "worst" | "best";
  automatic_selection: boolean;
  dte_min: number;
  dte_max: number;
  delta_min: number;
  delta_max: number;
  target_delta: number;
  iv_min: number;
  iv_max: number;
  previous_day_volume_min: number;
  preferred_width: number;
  fallback_width: number;
  risk_per_position: number;
  max_open_risk: number;
  max_open_securities: number;
  similarity_limit: number;
  fee_per_leg: number;
  risk_free_rate: number;
  dividend_yield: number;
  cash_interest_rate: number;
  symbols: string[];
  watchlist: string[];
  benchmark_security_id: string | null;
}

export interface OptionsBacktestResult {
  run_id?: string;
  specification: OptionsBacktestSpecification;
  summary: {
    worst_net_pnl: number;
    best_net_pnl: number;
    portfolio_rom_pct: number;
    win_rate_pct: number;
    winning_trades: number;
    losing_trades: number;
    total_trades: number;
    max_drawdown_pct: number;
    total_slippage_drag: number;
    overall_reliability_pct: number;
    rejection_counts: Record<string, number>;
  };
  positions: OptionsSpreadPosition[];
  best_positions: OptionsSpreadPosition[];
  blocked_candidates: Array<{ timestamp: string; security_id: string; reason: string; rule: string }>;
  warnings: string[];
  manifest: {
    kind?: string;
    provider?: string;
    source_sha256?: string;
    input_dataset_versions?: Record<string, string>;
  };
  equity_curve: object[];
  benchmark_equity_curve: object[];
}

export type Signal = AnySchema;
export type SignalRefreshFailure = AnySchema;
export type SignalRefresh = AnySchema;
export type DefinitionRevision = components["schemas"]["DefinitionRevisionResponse"];
export type EnabledStrategy = components["schemas"]["EnabledStrategyResponse"];

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly cause?: unknown,
    public readonly diagnosticId?: string,
  ) {
    super(message, cause !== undefined ? { cause } : undefined);
  }
}

const client = createClient<paths>({ baseUrl: "" });
// SAFETY: untypedClient provides fallback access to routes under active evolution
const untypedClient: any = client;

interface ApiErrorPayload {
  message?: string;
  detail?: string | Array<{ msg?: string } | string>;
}

function parseErrorMessage(cause: unknown, fallback: string): string {
  if (cause instanceof Error) {
    return cause.message;
  }
  if (cause && Object.prototype.toString.call(cause) === "[object Object]") {
    // SAFETY: Verified cause is an error payload object
    const payload = cause as ApiErrorPayload;
    if (payload.message) {
      return String(payload.message);
    }
    if (payload.detail) {
      if (Array.isArray(payload.detail)) {
        return payload.detail
          .map((item) => {
            if (item && Object.prototype.toString.call(item) === "[object Object]") {
              // SAFETY: Item is a validation error object with msg field
              const errObj = item as { msg?: string };
              return errObj.msg ? String(errObj.msg) : JSON.stringify(item);
            }
            return String(item);
          })
          .join("; ");
      }
      return String(payload.detail);
    }
  }
  return fallback;
}

async function dataOrThrow<T>(request: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await request;
  if (data !== undefined) return data;
  if (response.ok) {
    // SAFETY: Successful 204 responses have no body and callers only use the completion signal.
    return undefined as T;
  }
  const fallback = response.statusText || `Request failed with status ${response.status}`;
  const message = parseErrorMessage(error, fallback);
  const diagnosticId = response.headers.get("X-Diagnostic-ID") ?? undefined;
  const messageWithDiagnosticId = diagnosticId ? `${message} (Diagnostic ID: ${diagnosticId})` : message;
  throw new ApiError(response.status, messageWithDiagnosticId, error, diagnosticId);
}

export const api = {
  health: () => dataOrThrow(client.GET("/api/health")),
  listProjects: () => dataOrThrow(client.GET("/api/projects")),
  createProject: (project: ProjectCreate) => dataOrThrow(client.POST("/api/projects", { body: project })),
  saveDefinition: (projectId: string, definition: DefinitionCreate) =>
    dataOrThrow(
      client.POST("/api/projects/{project_id}/definitions", {
        params: { path: { project_id: projectId } },
        body: definition,
      }),
    ),
  renameProject: (projectId: string, request: { name: string }) =>
    dataOrThrow(
      client.PATCH("/api/projects/{project_id}", {
        params: { path: { project_id: projectId } },
        body: request,
      }),
    ),
  deleteProject: (projectId: string) =>
    dataOrThrow(
      client.DELETE("/api/projects/{project_id}", {
        params: { path: { project_id: projectId } },
      }),
    ),
  listRuns: (projectId: string) =>
    dataOrThrow(
      client.GET("/api/projects/{project_id}/runs", {
        params: { path: { project_id: projectId } },
      }),
    ),
  deleteRun: (projectId: string, runId: string) =>
    dataOrThrow(
      client.DELETE("/api/projects/{project_id}/runs/{run_id}", {
        params: { path: { project_id: projectId, run_id: runId } },
      }),
    ),
  bulkDeleteRuns: (projectId: string, runIds: string[]) =>
    dataOrThrow(
      client.POST("/api/projects/{project_id}/runs/bulk-delete", {
        params: { path: { project_id: projectId } },
        body: { run_ids: runIds },
      }),
    ),
  importDataset: (source: string, file: File) => {
    const formData = new FormData();
    formData.append("source", source);
    formData.append("file", file);
    return dataOrThrow(
      untypedClient.POST("/api/datasets", {
        body: formData,
        bodySerializer: (body: any) => body,
      }),
    );
  },
  getSecurityLists: () => dataOrThrow(client.GET("/api/security-lists")),
  downloadDataset: (request: ProviderDownloadRequest) =>
    dataOrThrow(
      client.POST("/api/datasets/download", {
        body: request,
      }),
    ),
  startDownload: (request: CompositeDownloadRequest) =>
    dataOrThrow(
      client.POST("/api/downloads", {
        body: request,
      }),
    ),
  getLatestDownload: () => dataOrThrow(client.GET("/api/downloads/latest")),
  getDownloadStatus: (downloadId: string) =>
    dataOrThrow(
      client.GET("/api/downloads/{download_id}", {
        params: { path: { download_id: downloadId } },
      }),
    ),
  cancelDownload: (downloadId: string) =>
    dataOrThrow(
      client.POST("/api/downloads/{download_id}/cancel", {
        params: { path: { download_id: downloadId } },
      }),
    ),
  getCoverage: (datasetVersionId: string) =>
    dataOrThrow(
      client.GET("/api/datasets/{dataset_version_id}/coverage", {
        params: { path: { dataset_version_id: datasetVersionId } },
      }),
    ),
  listDatasets: () => dataOrThrow(client.GET("/api/datasets")),
  deleteDataset: (datasetVersionId: string, force: boolean = true) =>
    dataOrThrow(
      client.DELETE("/api/datasets/{dataset_version_id}", {
        params: {
          path: { dataset_version_id: datasetVersionId },
          query: { force },
        },
      }),
    ),
  bulkDeleteDatasets: (datasetVersionIds: string[], force: boolean = true) =>
    dataOrThrow(
      client.POST("/api/datasets/bulk-delete", {
        body: { dataset_version_ids: datasetVersionIds, force },
      }),
    ),
  getPreview: (datasetVersionId: string) =>
    // SAFETY: Preview endpoint returns a list of dynamic row objects
    dataOrThrow(
      client.GET("/api/datasets/{dataset_version_id}/preview", {
        params: { path: { dataset_version_id: datasetVersionId } },
      }),
    ) as Promise<Record<string, string | number | boolean | null>[]>,
  getHistory: (datasetVersionId: string, params?: { as_of?: string; symbol?: string }) =>
    dataOrThrow(
      client.GET("/api/datasets/{dataset_version_id}/history", {
        params: {
          path: { dataset_version_id: datasetVersionId },
          query: params,
        },
      }),
    ),
  getFundamentals: (datasetVersionId: string, params?: { as_of?: string; symbol?: string }) =>
    dataOrThrow(
      client.GET("/api/datasets/{dataset_version_id}/fundamentals", {
        params: {
          path: { dataset_version_id: datasetVersionId },
          query: params,
        },
      }),
    ),
  getCorporateActions: (datasetVersionId: string, params?: { as_of?: string; symbol?: string }) =>
    dataOrThrow(
      client.GET("/api/datasets/{dataset_version_id}/corporate-actions", {
        params: {
          path: { dataset_version_id: datasetVersionId },
          query: params,
        },
      }),
    ),
  listSecurities: (params?: { query?: string; limit?: number }) =>
    dataOrThrow(
      client.GET("/api/securities", {
        params: { query: params },
      }),
    ),
  calculateComparableValuation: (request: {
    target_security_id: string;
    peer_security_ids: string[];
  }) =>
    dataOrThrow(
      untypedClient.POST("/api/valuations/comparables", {
        body: request,
      }),
    ),
  saveComparableValuation: (projectId: string, request: {
    target_security_id: string;
    peer_security_ids: string[];
  }) =>
    dataOrThrow(
      untypedClient.POST("/api/projects/{project_id}/valuations/comparables", {
        params: { path: { project_id: projectId } },
        body: request,
      }),
    ),
  seedDcfValuation: (projectId: string, securityId: string) =>
    dataOrThrow(
      untypedClient.GET("/api/projects/{project_id}/valuations/seed/{security_id}", {
        params: {
          path: { project_id: projectId, security_id: securityId },
        },
      }),
    ),
  calculateDcfValuation: (request: FCFFDCFRequest) =>
    dataOrThrow(
      untypedClient.POST("/api/valuations/dcf", {
        body: request,
      }),
    ),
  saveDcfValuation: (projectId: string, request: FCFFDCFRequest) =>
    dataOrThrow(
      untypedClient.POST("/api/projects/{project_id}/valuations/dcf", {
        params: { path: { project_id: projectId } },
        body: request,
      }),
    ),
  compareValuations: (projectId: string, request: { run_ids: string[] }) =>
    dataOrThrow(
      untypedClient.POST("/api/projects/{project_id}/valuations/compare", {
        params: { path: { project_id: projectId } },
        body: request,
      }),
    ),
  listValuations: (projectId: string) =>
    dataOrThrow(
      untypedClient.GET("/api/projects/{project_id}/valuations", {
        params: { path: { project_id: projectId } },
      }),
    ),
  getSecurityDetails: (securityId: string, params?: { project_id?: string }) =>
    dataOrThrow(
      client.GET("/api/securities/{security_id}", {
        params: {
          path: { security_id: securityId },
          query: params,
        },
      }),
    ),
  getWatchlist: (
    projectId: string,
    params?: {
      query?: string;
      exchange?: string;
      thesis_status?: string;
      sort_by?: string;
      sort_order?: string;
      offset?: number;
      limit?: number;
    },
  ) =>
    dataOrThrow(
      client.GET("/api/projects/{project_id}/watchlist", {
        params: {
          path: { project_id: projectId },
          query: params,
        },
      }),
    ),
  addToWatchlist: (projectId: string, request: { identifier: string }) =>
    dataOrThrow(
      client.POST("/api/projects/{project_id}/watchlist", {
        params: { path: { project_id: projectId } },
        body: request,
      }),
    ),
  removeFromWatchlist: (projectId: string, securityId: string) =>
    dataOrThrow(
      client.DELETE("/api/projects/{project_id}/watchlist/{security_id}", {
        params: {
          path: { project_id: projectId, security_id: securityId },
        },
      }),
    ),
  getThesis: (projectId: string, securityId: string) =>
    dataOrThrow(
      untypedClient.GET("/api/projects/{project_id}/research/{security_id}", {
        params: {
          path: { project_id: projectId, security_id: securityId },
        },
      }),
    ),
  saveThesis: (projectId: string, securityId: string, request: { content: string }) =>
    dataOrThrow(
      untypedClient.PUT("/api/projects/{project_id}/research/{security_id}", {
        params: {
          path: { project_id: projectId, security_id: securityId },
        },
        body: request,
      }),
    ),
  listIndicators: () => dataOrThrow(untypedClient.GET("/api/indicators")),
  getIndicator: (name: string) =>
    dataOrThrow(
      client.GET("/api/indicators/{name}", {
        params: { path: { name } },
      }),
    ),
  calculateIndicator: (request: IndicatorCalculateRequest) =>
    dataOrThrow(
      client.POST("/api/indicators/calculate", {
        body: request,
      }),
    ),
  listPredictiveModels: () => dataOrThrow(untypedClient.GET("/api/predictive-models")),
  getPredictiveModel: (name: string) =>
    dataOrThrow(
      untypedClient.GET("/api/predictive-models/{name}", {
        params: { path: { name } },
      }),
    ),
  previewPredictiveModel: (request: PredictiveModelRunRequest) =>
    dataOrThrow(
      untypedClient.POST("/api/predictive-models/run", {
        body: request,
      }),
    ),
  runPredictiveModel: (projectId: string, request: PredictiveModelRunRequest) =>
    dataOrThrow(
      untypedClient.POST("/api/projects/{project_id}/predictive-models/runs", {
        params: { path: { project_id: projectId } },
        body: request,
      }),
    ),
  listPredictiveModelRuns: (projectId: string) =>
    dataOrThrow(
      untypedClient.GET("/api/projects/{project_id}/predictive-models/runs", {
        params: { path: { project_id: projectId } },
      }),
    ),
  getPredictiveModelRun: (projectId: string, runId: string) =>
    dataOrThrow(
      untypedClient.GET("/api/projects/{project_id}/predictive-models/runs/{run_id}", {
        params: { path: { project_id: projectId, run_id: runId } },
      }),
    ),
  listStrategies: () => dataOrThrow(client.GET("/api/strategies")),
  getStrategyTemplate: () => dataOrThrow(client.GET("/api/strategies-meta/template")),
  getStrategy: (name: string) =>
    dataOrThrow(
      client.GET("/api/strategies/{name}", {
        params: { path: { name } },
      }),
    ),
  evaluateStrategy: (request: StrategyEvaluateRequest) =>
    dataOrThrow(
      client.POST("/api/strategies/evaluate", {
        body: request,
      }),
    ),
  saveStrategyEvaluation: (projectId: string, request: StrategyEvaluateRequest) =>
    dataOrThrow(
      client.POST("/api/projects/{project_id}/strategies/evaluate", {
        params: { path: { project_id: projectId } },
        body: request,
      }),
    ),
  getValuationExportUrl: (projectId: string, runId: string, format: "html" | "csv" | "json") =>
    `/api/projects/${encodeURIComponent(projectId)}/valuations/${encodeURIComponent(runId)}/export/${format}`,
  listAlerts: (projectId: string) =>
    dataOrThrow(
      untypedClient.GET("/api/projects/{project_id}/alerts", {
        params: { path: { project_id: projectId } },
      }),
    ),
  refreshAlerts: (projectId: string) =>
    dataOrThrow(
      untypedClient.POST("/api/projects/{project_id}/alerts/refresh", {
        params: { path: { project_id: projectId } },
      }),
    ),
  listEnabledStrategies: (projectId: string) =>
    dataOrThrow(
      client.GET("/api/projects/{project_id}/strategies/enabled", {
        params: { path: { project_id: projectId } },
      }),
    ),
  runOptionsBacktest: (projectId: string, request: OptionsBacktestRequest) =>
    dataOrThrow<OptionsBacktestResult>(
      untypedClient.POST("/api/projects/{project_id}/options-backtests", {
        params: { path: { project_id: projectId } },
        body: request,
      }),
    ),
  listOptionsBacktests: (projectId: string) =>
    dataOrThrow<OptionsBacktestResult[]>(
      untypedClient.GET("/api/projects/{project_id}/options-backtests", {
        params: { path: { project_id: projectId } },
      }),
    ),
  getOptionsBacktest: (projectId: string, runId: string) =>
    dataOrThrow<OptionsBacktestResult>(
      untypedClient.GET("/api/projects/{project_id}/runs/{run_id}/options_backtest", {
        params: { path: { project_id: projectId, run_id: runId } },
      }),
    ),
  getOptionsBacktestExportUrl: (projectId: string, runId: string, format: "html" | "csv" | "json") =>
    `/api/projects/${encodeURIComponent(projectId)}/options-backtests/${encodeURIComponent(runId)}/export/${format}`,
  getDefinitionRevision: (projectId: string, kind: string, name: string, revision: string) =>
    dataOrThrow(
      client.GET("/api/projects/{project_id}/definitions/{kind}/{name}/{revision}", {
        params: { path: { project_id: projectId, kind, name, revision } },
      }),
    ),
  evaluateVerdict: (projectId: string, request: StrategyVerdictRequest) =>
    dataOrThrow<StrategyVerdictResponse>(
      client.POST("/api/projects/{project_id}/backtests/verdict", {
        params: { path: { project_id: projectId } },
        body: request,
      }),
    ),
};
