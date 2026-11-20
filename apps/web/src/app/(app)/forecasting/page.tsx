"use client";

import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/app-shell";
import { ChartFrame } from "@/components/charts";
import { ForecastChart } from "@/components/forecast-charts";
import { useOrg } from "@/components/org-context";
import { Alert, Badge, Button, Card, EmptyState } from "@/components/ui";
import { fmtDateTime, fmtMonth, fmtNumber, fmtPct } from "@/lib/format";
import type { ForecastBundle, ForecastPoint } from "@/lib/types";

const eur = (v: number) => `€${v.toFixed(2)}`;
const pct = (v: string | null) => (v === null ? "—" : `${(Number(v) * 100).toFixed(0)}%`);

function QualityBadge({ f }: { f: ForecastPoint }) {
  return f.quality === "reliable" ? (
    <Badge tone="positive">beats baseline</Badge>
  ) : (
    <Badge tone="warning">not better than baseline</Badge>
  );
}

export default function ForecastingPage() {
  const { api, me, current } = useOrg();
  const [data, setData] = useState<ForecastBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [horizon, setHorizon] = useState(3);
  const [starting, setStarting] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await api<ForecastBundle>("/forecasts/latest"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load forecasts");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current.organization_id]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial data load
    void load();
  }, [load]);

  // while a run is in progress, refresh every 10 s
  useEffect(() => {
    if (!data?.running) return;
    const t = setInterval(() => void load(), 10_000);
    return () => clearInterval(t);
  }, [data?.running, load]);

  async function runNow() {
    setStarting(true);
    setError(null);
    try {
      await api("/admin/forecasts/run", { method: "POST" });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the forecast");
    } finally {
      setStarting(false);
    }
  }

  const run = data?.run;
  const last = run?.last_value ? Number(run.last_value) : null;
  const fcs = data?.forecasts ?? [];
  const allBelow = fcs.length > 0 && fcs.every((f) => f.quality !== "reliable");
  const someBelow = fcs.some((f) => f.quality !== "reliable");
  const history = (data?.history ?? []).slice(-36).map((p) => ({ date: p.date, value: Number(p.value) }));
  const band = fcs.map((f) => ({ date: f.target_date, value: Number(f.value), lower: Number(f.lower), upper: Number(f.upper) }));
  const backtests = (data?.backtests ?? []).filter((b) => b.horizon_months === horizon);

  return (
    <>
      <PageHeader
        title="Forecasting"
        description="1, 3 and 6-month forecasts of the EU import benchmark, tested against simple baselines."
        actions={
          me.is_platform_admin ? (
            <Button variant="secondary" onClick={runNow} disabled={starting || data?.running}>
              {data?.running ? "Forecast running…" : starting ? "Starting…" : "Run forecast now"}
            </Button>
          ) : undefined
        }
      />
      <div className="space-y-4">
        {error && <Alert>{error}</Alert>}
        {data?.running && (
          <Alert tone="warning">A new forecast is being computed (backtesting six models takes a few minutes). This page refreshes automatically.</Alert>
        )}
        {data?.last_failed_run && !data.running && (
          <Alert>
            The latest forecast run ({fmtDateTime(data.last_failed_run.generated_at)}) failed
            {run ? "; the previous forecast is shown below." : "."}
            {me.is_platform_admin && data.last_failed_run.error && (
              <span className="mt-1 block break-words font-mono text-[11px]">{data.last_failed_run.error.slice(0, 400)}</span>
            )}
          </Alert>
        )}
        {data && !run && !data.running && (
          <Card>
            <EmptyState title="No forecast yet">
              Forecasts are generated after each market-data import, once enough validated monthly history is available.
            </EmptyState>
          </Card>
        )}
        {run?.status === "insufficient_data" && (
          <Card>
            <EmptyState title="Not enough history to forecast">{run.notes.join(" ")}</EmptyState>
          </Card>
        )}

        {run?.status === "success" && fcs.length > 0 && (
          <>
            {allBelow ? (
              <Alert tone="warning">
                No statistical model beat the naive baseline in backtesting. The figures below are the baseline itself (“no change”)
                and must not be read as a prediction.
              </Alert>
            ) : someBelow ? (
              <Alert tone="warning">At some horizons no model beat the baseline; those horizons are marked and show the baseline.</Alert>
            ) : null}

            <section aria-label="Forecasts" className="grid grid-cols-1 gap-3 md:grid-cols-3">
              {fcs.map((f) => (
                <div key={f.horizon_months} className="rounded-lg border border-border bg-surface p-4">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-xs font-medium text-muted">
                      {f.horizon_months}-month forecast · {fmtMonth(f.target_date, "long")}
                    </p>
                    <Badge tone="accent">forecast</Badge>
                  </div>
                  <p className="mt-2 text-2xl font-semibold tracking-tight tabular-nums">
                    {eur(Number(f.value))}<span className="ml-1 text-sm font-normal text-muted">/{run.unit}</span>
                  </p>
                  <p className="mt-1 text-xs text-muted">
                    {last ? `${fmtPct(((Number(f.value) - last) / last) * 100)} vs ${fmtMonth(run.last_date, "long")}` : ""} ·{" "}
                    {Math.round(Number(f.interval_level ?? 0.8) * 100)}% range {eur(Number(f.lower))}–{eur(Number(f.upper))}
                  </p>
                  <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-subtle">
                    <QualityBadge f={f} />
                    <span>
                      {f.model_label}
                      {f.quality === "reliable" && f.improvement_pct && ` · ${f.improvement_pct}% lower error than the ${f.baseline_label ?? f.baseline} baseline`}
                    </span>
                  </div>
                </div>
              ))}
            </section>

            <ChartFrame
              title="Forecast vs history (EUR/kg)"
              table={
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-surface">
                    <tr className="border-b border-border text-left text-muted">
                      <th className="py-1.5 pr-3 font-medium">Month</th>
                      <th className="py-1.5 pr-3 text-right font-medium">Observed</th>
                      <th className="py-1.5 pr-3 text-right font-medium">Forecast</th>
                      <th className="py-1.5 pr-3 text-right font-medium">Range</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border tabular-nums">
                    {[...band].reverse().map((b) => (
                      <tr key={b.date}>
                        <td className="py-1.5 pr-3">{fmtMonth(b.date, "long")}</td>
                        <td className="py-1.5 pr-3 text-right">—</td>
                        <td className="py-1.5 pr-3 text-right">{eur(b.value)}</td>
                        <td className="py-1.5 pr-3 text-right">{eur(b.lower)} – {eur(b.upper)}</td>
                      </tr>
                    ))}
                    {[...history].reverse().map((h) => (
                      <tr key={h.date}>
                        <td className="py-1.5 pr-3">{fmtMonth(h.date, "long")}</td>
                        <td className="py-1.5 pr-3 text-right">{eur(h.value)}</td>
                        <td className="py-1.5 pr-3 text-right">—</td>
                        <td className="py-1.5 pr-3 text-right">—</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              }
              caption={
                <>
                  {data!.series_label}
                  {data!.scope ? ` · ${data!.scope.split(" - ")[0]}` : ""}. The shaded range is where the actual value fell in about{" "}
                  {Math.round(Number(fcs[0].interval_level ?? 0.8) * 100)}% of past forecasts (empirical interval from backtest errors).
                </>
              }
            >
              <ForecastChart history={history} forecast={band} valueFormat={eur} historyLabel="Observed (validated months)" />
            </ChartFrame>

            <Card title="Scenarios">
              <div className="-mx-5 overflow-x-auto">
                <table className="w-full min-w-[640px] text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs text-muted">
                      <th className="px-5 py-2 font-medium">Horizon</th>
                      <th className="px-3 py-2 text-right font-medium">Lower prices</th>
                      <th className="px-3 py-2 text-right font-medium">Base</th>
                      <th className="px-3 py-2 text-right font-medium">Higher prices</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border tabular-nums">
                    {fcs.map((f) => {
                      const sc = (k: string) => data!.scenarios.find((s) => s.horizon_months === f.horizon_months && s.key === k)!;
                      return (
                        <tr key={f.horizon_months}>
                          <td className="px-5 py-2">{f.horizon_months} month{f.horizon_months > 1 ? "s" : ""} · {fmtMonth(f.target_date)}</td>
                          {["downside", "base", "upside"].map((k) => (
                            <td key={k} className="px-3 py-2 text-right">
                              {eur(Number(sc(k).price))} <span className="text-xs text-muted">({fmtPct(sc(k).change_pct)})</span>
                            </td>
                          ))}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 text-xs leading-relaxed text-muted">
                How the scenarios are built: the base case is the selected model’s forecast; “lower” and “higher” are the bounds of its
                {" "}{Math.round(Number(fcs[0].interval_level ?? 0.8) * 100)}% prediction interval, measured from the model’s own errors in
                backtesting. Changes are versus the last observed month ({fmtMonth(run.last_date, "long")}, {eur(last ?? 0)}). No scenario
                is written by an AI.
              </p>
            </Card>

            <Card
              title="Model performance (rolling-origin backtest)"
              action={
                <div className="inline-flex rounded-md border border-border p-0.5 text-xs" role="group" aria-label="Horizon">
                  {[1, 3, 6].map((h) => (
                    <button
                      key={h}
                      onClick={() => setHorizon(h)}
                      aria-pressed={horizon === h}
                      className={`rounded px-2 py-1 ${horizon === h ? "bg-accent-soft font-medium text-accent" : "text-muted hover:text-foreground"}`}
                    >
                      {h}M
                    </button>
                  ))}
                </div>
              }
            >
              <div className="-mx-5 overflow-x-auto">
                <table className="w-full min-w-[720px] text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs text-muted">
                      <th className="px-5 py-2 font-medium">Model</th>
                      <th className="px-3 py-2 text-right font-medium">MAE (€/kg)</th>
                      <th className="px-3 py-2 text-right font-medium">WAPE</th>
                      <th className="px-3 py-2 text-right font-medium">Direction right</th>
                      <th className="px-3 py-2 text-right font-medium">Interval coverage</th>
                      <th className="px-5 py-2 text-right font-medium">Tests</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border tabular-nums">
                    {backtests.map((b) => (
                      <tr key={b.model} className={b.selected ? "bg-accent-soft/40" : ""}>
                        <td className="px-5 py-2">
                          <span className={b.selected ? "font-medium" : ""}>{b.model_label}</span>
                          {b.is_baseline && <span className="ml-2"><Badge>baseline</Badge></span>}
                          {b.selected && <span className="ml-2"><Badge tone="accent">selected</Badge></span>}
                        </td>
                        <td className="px-3 py-2 text-right">{fmtNumber(b.mae, 3)}</td>
                        <td className="px-3 py-2 text-right">{pct(b.wape)}</td>
                        <td className="px-3 py-2 text-right">{b.directional_accuracy === null ? "n/a" : pct(b.directional_accuracy)}</td>
                        <td className="px-3 py-2 text-right">{pct(b.interval_coverage)}</td>
                        <td className="px-5 py-2 text-right text-muted">{b.n_origins}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 text-xs leading-relaxed text-muted">
                Each model forecast every past month from data available at that time only, then was compared with what happened.
                MAE: average error in €/kg. WAPE: total error as a share of actual values. Direction: how often the predicted rise or
                fall matched (not applicable to the naive model, which predicts no change). Coverage: how often the actual value fell
                inside the stated interval (target {Math.round(Number(fcs[0].interval_level ?? 0.8) * 100)}%). A model is used only if
                its MAE is lower than the best baseline’s.
              </p>
            </Card>
          </>
        )}

        {run && (
          <Card title="Run information">
            <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-xs sm:grid-cols-[auto_1fr]">
              <dt className="text-muted">Generated</dt>
              <dd>{fmtDateTime(run.generated_at)}</dd>
              <dt className="text-muted">Data used</dt>
              <dd>{run.n_observations} months, {fmtMonth(run.first_date, "long")} – {fmtMonth(run.last_date, "long")}</dd>
              <dt className="text-muted">Input data version</dt>
              <dd className="break-all font-mono">{run.input_data_version ?? "—"}</dd>
              <dt className="text-muted">Model version</dt>
              <dd className="font-mono">{run.model_version}</dd>
              {run.notes.length > 0 && (
                <>
                  <dt className="text-muted">Data notes</dt>
                  <dd>{run.notes.join("; ")}</dd>
                </>
              )}
            </dl>
          </Card>
        )}
        {!data && !error && <div className="h-64 animate-pulse rounded-lg border border-border bg-surface" />}
      </div>
    </>
  );
}
