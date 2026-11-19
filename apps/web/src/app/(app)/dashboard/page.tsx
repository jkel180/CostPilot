"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/app-shell";
import { useOrg } from "@/components/org-context";
import { Alert, Badge, Card, EmptyState } from "@/components/ui";
import type { DashboardSummary, Kpi } from "@/lib/types";

const KIND_TONE = { observed: "neutral", forecast: "accent", calculated: "positive" } as const;

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

function KpiCard({ kpi }: { kpi: Kpi }) {
  const available = kpi.status === "available" && kpi.value !== null;
  return (
    <div className="flex min-h-[124px] flex-col rounded-lg border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium text-muted">{kpi.label}</p>
        {kpi.value_kind && <Badge tone={KIND_TONE[kpi.value_kind]}>{kpi.value_kind}</Badge>}
      </div>
      {available ? (
        <>
          <p className="mt-2 text-2xl font-semibold tracking-tight">
            {Number(kpi.value).toLocaleString("en-GB", { maximumFractionDigits: 2 })}
            <span className="ml-1 text-sm font-normal text-muted">
              {kpi.currency}/{kpi.unit}
            </span>
          </p>
          {kpi.provenance && (
            <p className="mt-auto pt-2 text-[11px] text-subtle">
              {kpi.provenance.source_name} · {formatDate(kpi.provenance.observation_date)}
              {kpi.provenance.is_synthetic && <span className="ml-1 font-semibold text-warning">SYNTHETIC</span>}
            </p>
          )}
        </>
      ) : (
        <>
          <p className="mt-2 text-2xl font-semibold text-subtle">—</p>
          <p className="mt-auto pt-2 text-[11px] leading-snug text-subtle">{kpi.reason ?? "Not available"}</p>
        </>
      )}
    </div>
  );
}

function ChartPanel({ title, empty }: { title: string; empty: string }) {
  return (
    <Card title={title}>
      <div className="h-56">
        <EmptyState title="No data to plot yet">{empty}</EmptyState>
      </div>
    </Card>
  );
}

function StatusRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2 text-sm">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right font-medium">{value}</dd>
    </div>
  );
}

export default function DashboardPage() {
  const { api, current } = useOrg();
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<DashboardSummary>("/dashboard/summary")
      .then(setData)
      .catch((e: Error) => setError(e.message));
    // api is re-created per render; the org id is the real dependency (page remounts on switch)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current.organization_id]);

  const ds = data?.data_status;
  return (
    <>
      <PageHeader
        title={data ? data.commodity.name : "Dashboard"}
        description="Market benchmark, forecasts and your cost exposure at a glance."
      />
      {error && (
        <div className="mb-6">
          <Alert>{error}</Alert>
        </div>
      )}
      {ds?.synthetic_data_present && (
        <div className="mb-6">
          <Alert tone="warning">
            This environment contains synthetic development data. It is not real market information.
          </Alert>
        </div>
      )}

      <section aria-label="Key indicators" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
        {(data?.kpis ?? []).map((k) => (
          <KpiCard key={k.key} kpi={k} />
        ))}
        {!data &&
          !error &&
          Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="h-[124px] animate-pulse rounded-lg border border-border bg-surface" />
          ))}
      </section>

      <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <ChartPanel title="Historical Price Trend" empty="Appears once validated market observations are imported (Sprint 2)." />
        <ChartPanel title="Forecast vs Historical Price" empty="Appears once forecasts pass backtesting against baselines (Sprint 3)." />
        <ChartPanel title="Market vs Customer Price" empty="Compares your purchase prices with benchmarks of the same specification." />
        <ChartPanel title="Cost Impact Scenarios" empty="Appears once a cost model with your expected volumes is set up (Sprint 3)." />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-4">
        <Card title="Market Overview">
          <EmptyState title="No market overview yet">Built from validated observations and documented sources.</EmptyState>
        </Card>
        <Card title="Latest Insights">
          <EmptyState title="No insights yet">AI explanations use only CostPilot data and cite their sources.</EmptyState>
        </Card>
        <Card title="Active Alerts">
          {data && data.active_alerts > 0 ? (
            <p className="text-sm">
              <span className="text-2xl font-semibold">{data.active_alerts}</span>{" "}
              <span className="text-muted">active alert rule{data.active_alerts === 1 ? "" : "s"}</span>
            </p>
          ) : (
            <EmptyState title="No active alerts">Threshold and % change alerts arrive in Sprint 4.</EmptyState>
          )}
        </Card>
        <Card title="Data Update Status">
          {ds ? (
            <dl className="divide-y divide-border">
              <StatusRow label="Market observations" value={ds.market_observations.toLocaleString("en-GB")} />
              <StatusRow label="Latest observation" value={formatDate(ds.latest_observation_date)} />
              <StatusRow label="Last collected" value={formatDate(ds.latest_collected_at)} />
              <StatusRow label="Active sources" value={ds.active_sources} />
              <StatusRow label="Your purchase records" value={ds.customer_purchases.toLocaleString("en-GB")} />
              <StatusRow label="Latest purchase" value={formatDate(ds.latest_purchase_date)} />
            </dl>
          ) : (
            <div className="h-40 animate-pulse rounded bg-background" />
          )}
        </Card>
      </div>
    </>
  );
}
