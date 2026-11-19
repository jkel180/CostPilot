export type Role = "admin" | "analyst" | "viewer";

export type MembershipSummary = { organization_id: string; organization_name: string; role: Role };
export type Me = { user: { id: string; email: string; full_name: string | null }; memberships: MembershipSummary[] };

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
};

export const ROLE_LABEL: Record<Role, string> = { admin: "Admin", analyst: "Analyst", viewer: "Viewer" };
