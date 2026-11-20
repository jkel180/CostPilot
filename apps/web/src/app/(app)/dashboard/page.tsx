"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/app-shell";
import { ChartFrame, SERIES_COLORS, SeriesTable, TimeLineChart } from "@/components/charts";
import { ForecastChart, ImpactBars } from "@/components/forecast-charts";
import { useOrg } from "@/components/org-context";
import { Alert, Badge, Card, EmptyState } from "@/components/ui";
import { fmtPct } from "@/lib/format";
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
        <span className="flex flex-wrap justify-end gap-1">
          {kpi.quality === "below_baseline" && <Badge tone="warning">below baseline</Badge>}
          {kpi.value_kind && <Badge tone={KIND_TONE[kpi.value_kind]}>{kpi.value_kind}</Badge>}
        </span>
      </div>
      {available ? (
        <>
          <p className="mt-2 text-2xl font-semibold tracking-tight tabular-nums">
            {kpi.unit === "%" ? (
              fmtPct(kpi.value)
            ) : kpi.key === "estimated_cost_exposure" ? (
              <>
                {Number(kpi.value) > 0 ? "+" : Number(kpi.value) < 0 ? "−" : ""}
                {Math.abs(Number(kpi.value)).toLocaleString("en-GB", { maximumFractionDigits: 0 })}
                <span className="ml-1 text-sm font-normal text-muted">{kpi.currency} · {kpi.unit}</span>
              </>
            ) : (
              <>
                {Number(kpi.value).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                <span className="ml-1 text-sm font-normal text-muted">
                  {kpi.currency}/{kpi.unit}
                </span>
              </>
            )}
          </p>
          {kpi.note && <p className="mt-1 text-[11px] leading-snug text-muted">{kpi.note}</p>}
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
  const bench = data
    ? [{ key: "b", label: "Extra-EU imports", color: SERIES_COLORS[0], points: data.benchmark_series.map((p) => ({ date: p.date, value: Number(p.value) })) }]
    : [];
  // customer prices start the comparison window; the benchmark is trimmed to the same months
  const firstCustomer = data?.customer_series[0]?.date ?? "";
  const marketVsCustomer = data
    ? [
        { key: "m", label: "Market benchmark (customs)", color: SERIES_COLORS[0], points: (bench[0]?.points ?? []).filter((p) => p.date >= firstCustomer) },
        { key: "c", label: "Your weighted avg. price", color: SERIES_COLORS[1], points: data.customer_series.map((p) => ({ date: p.date, value: Number(p.value) })) },
      ]
    : [];
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
        {data && data.benchmark_series.length > 0 ? (
          <ChartFrame
            title="Historical Price Trend (EUR/kg)"
            table={<SeriesTable series={bench} valueFormat={(v) => `€${v.toFixed(2)}`} />}
            caption={
              <>
                {data.benchmark_label}, last {data.benchmark_series.length} validated months. Source: Eurostat Comext.{" "}
                <Link href="/market" className="text-accent hover:underline">Market details</Link>
              </>
            }
          >
            <TimeLineChart series={bench} valueFormat={(v) => `€${v.toFixed(2)}`} height={224} />
          </ChartFrame>
        ) : (
          <ChartPanel title="Historical Price Trend" empty="Appears once validated market observations are imported." />
        )}
        {data && data.forecast_points.length > 0 ? (
          <ChartFrame
            title="Forecast vs Historical Price (EUR/kg)"
            table={
              <SeriesTable
                series={[{ key: "f", label: "Forecast", color: SERIES_COLORS[0], points: data.forecast_points.map((f) => ({ date: f.target_date, value: Number(f.value) })) }]}
                valueFormat={(v) => `€${v.toFixed(2)}`}
              />
            }
            caption={
              <>
                {data.forecast_points.some((f) => f.quality !== "reliable")
                  ? "At some horizons no model beat the naive baseline: treat those values as 'no change'. "
                  : "Selected models beat the naive baselines in backtesting. "}
                Shaded: prediction interval. <Link href="/forecasting" className="text-accent hover:underline">Model details</Link>
              </>
            }
          >
            <ForecastChart
              history={bench[0]?.points.slice(-24) ?? []}
              forecast={data.forecast_points.map((f) => ({ date: f.target_date, value: Number(f.value), lower: Number(f.lower), upper: Number(f.upper) }))}
              valueFormat={(v) => `€${v.toFixed(2)}`}
              height={224}
            />
          </ChartFrame>
        ) : (
          <ChartPanel title="Forecast vs Historical Price" empty="Appears once a forecast has been generated and backtested against baselines." />
        )}
        {data && data.customer_series.length > 0 && data.benchmark_series.length > 0 ? (
          <ChartFrame
            title="Market vs Customer Price (EUR/kg)"
            table={<SeriesTable series={marketVsCustomer} valueFormat={(v) => `€${v.toFixed(2)}`} />}
            caption={
              <>
                Your monthly weighted average purchase price vs the EU customs import value. They are not the same price: the
                benchmark is a border value for a broader product code, your price includes delivery, specification and margins.
                Read the gap as a trend. Prices are compared only in EUR per kg (tonnes converted × 1/1000; other currencies and
                volume units are left out). {data.customer_series_note}
              </>
            }
          >
            <TimeLineChart series={marketVsCustomer} valueFormat={(v) => `€${v.toFixed(2)}`} height={224} />
          </ChartFrame>
        ) : (
          <ChartPanel
            title="Market vs Customer Price"
            empty={data?.customer_series_note ?? "Appears once purchases in EUR per mass unit are uploaded in My Purchases."}
          />
        )}
        {data && data.cost_scenarios.length > 0 ? (
          <ChartFrame
            title={`Cost Impact Scenarios, next ${data.cost_scenarios_months} months (${data.organization_currency})`}
            table={
              <table className="w-full text-xs">
                <tbody className="divide-y divide-border tabular-nums">
                  {data.cost_scenarios.map((s) => (
                    <tr key={s.key}><td className="py-1.5 pr-3">{s.label}</td><td className="py-1.5 text-right">{Math.round(Number(s.period_impact)).toLocaleString("en-GB")}</td></tr>
                  ))}
                </tbody>
              </table>
            }
            caption={<>From your cost model. <Link href="/simulator" className="text-accent hover:underline">Open Cost Simulator</Link></>}
          >
            <ImpactBars
              items={data.cost_scenarios.map((s) => ({ label: s.label, value: Number(s.period_impact), note: s.assumption }))}
              valueFormat={(v) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(Math.round(v)).toLocaleString("en-GB")}`}
            />
          </ChartFrame>
        ) : (
          <ChartPanel title="Cost Impact Scenarios" empty="Appears once your cost model is saved in Cost Simulator." />
        )}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-4">
        <Card title="Market Overview">
          {data && data.benchmark_series.length > 0 ? (
            <div className="space-y-2 text-sm">
              <p className="text-muted">
                EU import unit value for the latest month and its change. Origins, volumes and sources are on the market page.
              </p>
              <Link href="/market" className="inline-block font-medium text-accent hover:underline">Open Market Intelligence →</Link>
            </div>
          ) : (
            <EmptyState title="No market overview yet">Built from validated observations and documented sources.</EmptyState>
          )}
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
