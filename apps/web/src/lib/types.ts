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
