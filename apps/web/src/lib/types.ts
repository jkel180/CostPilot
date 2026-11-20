export type Role = "admin" | "analyst" | "viewer";

export type MembershipSummary = { organization_id: string; organization_name: string; role: Role };
export type Me = {
  user: { id: string; email: string; full_name: string | null };
  memberships: MembershipSummary[];
  is_platform_admin: boolean;
};

export type Organization = {
  id: string;
  name: string;
  country: string | null;
  currency: string;
  created_at: string;
  role?: Role;
};

export type Member = {
  membership_id: string;
  user_id: string;
  email: string;
  full_name: string | null;
  role: Role;
  joined_at: string;
};

export type Kpi = {
  key: string;
  label: string;
  status: "available" | "not_available";
  value: string | null;
  unit: string | null;
  currency: string | null;
  value_kind: "observed" | "forecast" | "calculated" | null;
  provenance: {
    source_name: string;
    data_type: string;
    observation_date: string;
    collected_at: string;
    is_synthetic: boolean;
  } | null;
  reason: string | null;
  note: string | null;
  quality?: string | null;
};

export type DashboardSummary = {
  commodity: { id: string; code: string; name: string; default_unit: string; default_currency: string };
  organization_currency: string;
  kpis: Kpi[];
  data_status: {
    market_observations: number;
    latest_observation_date: string | null;
    latest_collected_at: string | null;
    active_sources: number;
    synthetic_data_present: boolean;
    customer_purchases: number;
    latest_purchase_date: string | null;
  };
  active_alerts: number;
  benchmark_series: SeriesPoint[];
  benchmark_label: string | null;
  forecast_points: ForecastPoint[];
  customer_series: SeriesPoint[];
  customer_series_note: string | null;
  cost_scenarios: SimScenario[];
  cost_scenarios_months: number | null;
};

export const ROLE_LABEL: Record<Role, string> = { admin: "Admin", analyst: "Analyst", viewer: "Viewer" };

// ---------------------------------------------------------------- market data

export type SeriesPoint = {
  date: string;
  value: string;
  quality_status: "validated" | "unvalidated" | "rejected";
  quality_note?: string | null;
  quantity_kg?: string | null;
};

export type Series = { geography: string; label: string; points: SeriesPoint[] };

export type SeriesResponse = {
  commodity: string;
  data_type: string;
  unit: string | null;
  currency: string | null;
  scope: string | null;
  series: Series[];
};

export type SourceInfo = {
  id: string;
  name: string;
  source_type: string;
  source_url: string | null;
  license_reference: string | null;
  update_frequency: string | null;
  is_synthetic: boolean;
  observations: number;
  latest_observation_date: string | null;
  last_collected_at: string | null;
  last_run_status: string | null;
  last_run_at: string | null;
  last_success_at: string | null;
  last_data_version: string | null;
  last_error: string | null;
};

export type OriginRow = {
  geography: string;
  label: string;
  month: string;
  unit_value: string | null;
  unit_value_quality: string | null;
  quantity_kg: string | null;
  volume_share_pct: string | null;
  mom_pct: string | null;
};

export type MarketOverview = {
  commodity: string;
  benchmark_label: string;
  scope: string | null;
  latest_month: string | null;
  benchmark_value: string | null;
  benchmark_mom_pct: string | null;
  benchmark_yoy_pct: string | null;
  benchmark_12m_avg: string | null;
  import_volume_kg: string | null;
  import_volume_yoy_pct: string | null;
  origins: OriginRow[];
  sources: SourceInfo[];
};

export type IngestionRun = {
  id: string;
  connector: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  rows_fetched: number;
  rows_saved: number;
  rows_rejected: number;
  data_version: string | null;
  error: string | null;
};

// ---------------------------------------------------------------- purchases

export type PreviewRow = { line: number; values: Record<string, string> | null; errors: string[] };

export type ImportPreview = {
  filename: string;
  columns: string[];
  delimiter: string;
  number_format: string;
  mapping: Record<string, string | null>;
  required_fields: string[];
  optional_fields: string[];
  mapping_errors: string[];
  rows_total: number;
  rows_valid: number;
  rows_invalid: number;
  preview: PreviewRow[];
  errors: PreviewRow[];
};

export type PurchaseImport = {
  id: string;
  filename: string;
  rows_total: number;
  rows_imported: number;
  rows_skipped: number;
  created_at: string;
};

export type Purchase = {
  id: string;
  purchase_date: string;
  supplier: string;
  product_description: string;
  quantity: string;
  unit: string;
  unit_price: string;
  currency: string;
  brix: string | null;
  country_of_origin: string | null;
  incoterm: string | null;
  contract_type: string | null;
};

export type WappGroup = {
  key: string;
  unit: string;
  currency: string;
  purchases: number;
  total_quantity: string;
  total_spend: string;
  weighted_avg_price: string | null;
  min_price: string;
  max_price: string;
  first_purchase: string;
  last_purchase: string;
};

export type PurchaseAnalysis = {
  overall: WappGroup[];
  by_supplier: WappGroup[];
  by_product: WappGroup[];
  by_month: WappGroup[];
};

// ---------------------------------------------------------------- forecasts

export type ForecastPoint = {
  horizon_months: number;
  target_date: string;
  value: string;
  lower: string;
  upper: string;
  interval_level: string | null;
  model: string;
  model_label: string;
  quality: "reliable" | "below_baseline" | "insufficient_data";
  baseline: string | null;
  model_mae: string | null;
  baseline_mae: string | null;
  improvement_pct: string | null;
};

export type Backtest = {
  model: string;
  model_label: string;
  horizon_months: number;
  is_baseline: boolean;
  selected: boolean;
  n_origins: number;
  mae: string | null;
  wape: string | null;
  directional_accuracy: string | null;
  interval_coverage: string | null;
};

export type ForecastScenario = {
  key: "downside" | "base" | "upside";
  label: string;
  horizon_months: number;
  price: string;
  change_pct: string;
  assumption: string;
};

export type ForecastRunInfo = {
  id: string;
  status: string;
  generated_at: string;
  input_data_version: string | null;
  model_version: string;
  n_observations: number;
  first_date: string | null;
  last_date: string | null;
  last_value: string | null;
  currency: string | null;
  unit: string | null;
  notes: string[];
  settings: Record<string, unknown>;
  error: string | null;
};

export type ForecastBundle = {
  run: ForecastRunInfo | null;
  running: boolean;
  last_failed_run: ForecastRunInfo | null;
  series_label: string;
  scope: string | null;
  history: SeriesPoint[];
  forecasts: ForecastPoint[];
  backtests: Backtest[];
  scenarios: ForecastScenario[];
};

// ---------------------------------------------------------------- cost model

export type CostModel = {
  id: string;
  name: string;
  expected_volume: string;
  volume_period: "monthly" | "annual";
  current_purchase_price: string;
  target_purchase_price: string | null;
  currency: string;
  unit: string;
  pass_through_pct: string;
  commodity_cost_share_pct: string | null;
  notes: string | null;
  updated_at: string;
};

export type SimScenario = {
  key: string;
  label: string;
  source: "forecast" | "custom";
  assumption: string;
  benchmark_change_pct: string;
  price_change_pct: string;
  scenario_price: string;
  period_quantity: string;
  expected_spend: string;
  baseline_spend: string;
  period_impact: string;
  annualized_impact: string;
  forecast_quality: string | null;
};

export type SimulationResult = {
  inputs: Record<string, string | number>;
  inputs_source: "cost_model" | "request" | "mixed";
  monthly_quantity: string;
  currency: string;
  unit: string;
  months: number;
  market_gap: {
    available: boolean;
    customer_price_per_kg: string | null;
    benchmark_per_kg: string | null;
    benchmark_date: string | null;
    gap_pct: string | null;
    rule: string;
  };
  forecast_horizon_used: number | null;
  forecast_note: string | null;
  target_annual_savings: string | null;
  scenarios: SimScenario[];
};
