"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { PageHeader } from "@/components/app-shell";
import { ChartFrame, SERIES_COLORS, SeriesTable, TimeBarChart, TimeLineChart, type LineSeries } from "@/components/charts";
import { useOrg } from "@/components/org-context";
import { Alert, Badge, Button, Card, EmptyState, Field, Input } from "@/components/ui";
import { fmtDateTime, fmtMonth, fmtNumber, fmtPct, fmtTonnes } from "@/lib/format";
import type { IngestionRun, MarketOverview, SeriesResponse } from "@/lib/types";

const BENCH = "EXT_EU27_2020";
const RANGES = [
  { key: "2y", label: "2Y", months: 24 },
  { key: "5y", label: "5Y", months: 60 },
  { key: "all", label: "All", months: 0 },
] as const;

const eurKg = (v: number) => `€${v.toFixed(2)}`;

function Tile({ label, value, sub, kind }: { label: string; value: string; sub?: string; kind: "observed" | "calculated" }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium text-muted">{label}</p>
        <Badge tone={kind === "observed" ? "neutral" : "positive"}>{kind}</Badge>
      </div>
      <p className="mt-2 text-2xl font-semibold tracking-tight tabular-nums">{value}</p>
      {sub && <p className="mt-1 text-[11px] text-subtle">{sub}</p>}
    </div>
  );
}

function QualityBadge({ q }: { q: string | null }) {
  if (!q) return <span className="text-subtle">—</span>;
  return <Badge tone={q === "validated" ? "positive" : q === "rejected" ? "negative" : "warning"}>{q}</Badge>;
}

function AdminPanel({ onDone }: { onDone: () => void }) {
  const { api } = useOrg();
  const [busy, setBusy] = useState<"run" | "upload" | null>(null);
  const [msg, setMsg] = useState<{ tone: "positive" | "negative"; text: string } | null>(null);

  async function runComext() {
    setBusy("run");
    setMsg(null);
    try {
      const r = await api<IngestionRun>("/admin/ingestion/eurostat_comext", { method: "POST" });
      setMsg({ tone: "positive", text: `Eurostat import completed: ${r.rows_saved} observations saved, ${r.rows_rejected} records rejected.` });
      onDone();
    } catch (e) {
      setMsg({ tone: "negative", text: e instanceof Error ? e.message : "Import failed" });
    } finally {
      setBusy(null);
    }
  }

  async function upload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    setBusy("upload");
    setMsg(null);
    try {
      const r = await api<IngestionRun>("/admin/market-observations/upload", { method: "POST", body: new FormData(form) });
      setMsg({ tone: "positive", text: `Upload completed: ${r.rows_saved} observations saved, ${r.rows_rejected} rows rejected.` });
      form.reset();
      onDone();
    } catch (err) {
      setMsg({ tone: "negative", text: err instanceof Error ? err.message : "Upload failed" });
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card title="Data management" action={<Badge tone="accent">Platform admin</Badge>}>
      <div className="space-y-4">
        {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted">Fetch the latest monthly data from Eurostat Comext. Re-running updates existing months.</p>
          <Button onClick={runComext} disabled={busy !== null}>
            {busy === "run" ? "Importing…" : "Run Eurostat import"}
          </Button>
        </div>
        <form onSubmit={upload} className="grid gap-3 border-t border-border pt-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
          <Field label="Market observations CSV" hint="observation_date, geography, value, currency, unit, data_type">
            <Input name="file" type="file" accept=".csv,text/csv" required className="py-1.5" />
          </Field>
          <Field label="Original source" hint="Where the figures come from, e.g. broker report, May 2026">
            <Input name="original_source" required minLength={3} maxLength={300} />
          </Field>
          <Button type="submit" variant="secondary" disabled={busy !== null}>
            {busy === "upload" ? "Uploading…" : "Upload"}
          </Button>
        </form>
      </div>
    </Card>
  );
}

export default function MarketPage() {
  const { api, me, current } = useOrg();
  const [overview, setOverview] = useState<MarketOverview | null>(null);
  const [prices, setPrices] = useState<SeriesResponse | null>(null);
  const [volumes, setVolumes] = useState<SeriesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<(typeof RANGES)[number]["key"]>("2y");
  // compared origins keep their colour slot while selected (colour follows the entity)
  const [compare, setCompare] = useState<(string | null)[]>([null, null]);

  const load = useCallback(async () => {
    try {
      const [o, p, v] = await Promise.all([
        api<MarketOverview>("/market/overview"),
        api<SeriesResponse>("/market/series?data_type=customs_unit_value"),
        api<SeriesResponse>(`/market/series?data_type=trade_volume&geography=${BENCH}`),
      ]);
      setOverview(o);
      setPrices(p);
      setVolumes(v);
      setCompare((c) => (c[0] === null && c[1] === null && o.origins[0] ? [o.origins[0].geography, null] : c));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load market data");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current.organization_id]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial data load
    void load();
  }, [load]);

  const cutoff = useMemo(() => {
    const months = RANGES.find((r) => r.key === range)!.months;
    if (!months || !overview?.latest_month) return "";
    const d = new Date(`${overview.latest_month}T00:00:00Z`);
    d.setUTCMonth(d.getUTCMonth() - months + 1);
    return d.toISOString().slice(0, 10);
  }, [range, overview]);

  const lineSeries: LineSeries[] = useMemo(() => {
    if (!prices) return [];
    const pick = (geo: string, color: string): LineSeries | null => {
      const s = prices.series.find((x) => x.geography === geo);
      return s
        ? { key: geo, label: s.label, color, points: s.points.filter((p) => p.date >= cutoff).map((p) => ({ date: p.date, value: Number(p.value) })) }
        : null;
    };
    return [
      pick(BENCH, SERIES_COLORS[0]),
      ...compare.map((g, i) => (g ? pick(g, SERIES_COLORS[i + 1]) : null)),
    ].filter((s): s is LineSeries => s !== null);
  }, [prices, compare, cutoff]);

  const volumePoints = useMemo(
    () =>
      (volumes?.series[0]?.points ?? [])
        .filter((p) => p.date >= cutoff)
        .map((p) => ({ date: p.date, value: Number(p.value) / 1000 })),
    [volumes, cutoff],
  );

  const originsWithPrices = useMemo(
    () => (prices?.series ?? []).filter((s) => s.geography !== BENCH).map((s) => ({ geo: s.geography, label: s.label })),
    [prices],
  );

  const toggle = (geo: string) =>
    setCompare((c) => {
      if (c.includes(geo)) return c.map((g) => (g === geo ? null : g));
      const free = c.indexOf(null);
      return free === -1 ? c : c.map((g, i) => (i === free ? geo : g));
    });

  const hasData = overview?.latest_month;

  return (
    <>
      <PageHeader
        title="Market Intelligence"
        description="Lemon juice concentrate: EU import benchmarks, origins and data provenance."
        actions={
          hasData ? (
            <div className="inline-flex rounded-md border border-border bg-surface p-0.5 text-xs" role="group" aria-label="Time range">
              {RANGES.map((r) => (
                <button
                  key={r.key}
                  onClick={() => setRange(r.key)}
                  aria-pressed={range === r.key}
                  className={`rounded px-2.5 py-1 ${range === r.key ? "bg-accent-soft font-medium text-accent" : "text-muted hover:text-foreground"}`}
                >
                  {r.label}
                </button>
              ))}
            </div>
          ) : undefined
        }
      />
      <div className="space-y-4">
        {error && <Alert>{error}</Alert>}
        {me.is_platform_admin && <AdminPanel onDone={load} />}

        {overview && !hasData && (
          <Card>
            <EmptyState title="No market data yet">
              Market observations appear here once a platform administrator runs the Eurostat import.
            </EmptyState>
          </Card>
        )}

        {overview && hasData && (
          <>
            <div className="rounded-md border border-border bg-surface px-4 py-3 text-xs leading-relaxed text-muted">
              <span className="font-medium text-foreground">What this benchmark is: </span>
              the average customs value per kg of EU imports declared under {overview.scope?.split(" - ")[0] ?? "the product code"} (
              {overview.scope?.split(" - ")[1] ?? ""}). It is a border value of declared trade, not a spot or contract price, and the
              code also covers other single citrus juices besides lemon (e.g. lime). Compare it with your prices as a trend, not as an
              exact quote.
            </div>

            <section aria-label="Key indicators" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Tile label="Benchmark (extra-EU imports)" kind="observed" value={`${eurKg(Number(overview.benchmark_value))}/kg`} sub={fmtMonth(overview.latest_month, "long")} />
              <Tile label="Change vs previous month" kind="calculated" value={fmtPct(overview.benchmark_mom_pct)} sub={`Year on year: ${fmtPct(overview.benchmark_yoy_pct)}`} />
              <Tile label="12-month average" kind="calculated" value={overview.benchmark_12m_avg ? `${eurKg(Number(overview.benchmark_12m_avg))}/kg` : "—"} sub="Validated months only" />
              <Tile label="Extra-EU import volume" kind="observed" value={fmtTonnes(overview.import_volume_kg)} sub={`${fmtMonth(overview.latest_month, "long")} · YoY ${fmtPct(overview.import_volume_yoy_pct)}`} />
            </section>

            <ChartFrame
              title="Price history (EUR/kg)"
              controls={
                <div className="flex flex-wrap items-center gap-1.5" aria-label="Compare origins">
                  <span className="text-xs text-muted">Compare:</span>
                  {originsWithPrices.slice(0, 8).map((o) => {
                    const slot = compare.indexOf(o.geo);
                    const full = !compare.includes(null) && slot === -1;
                    return (
                      <button
                        key={o.geo}
                        onClick={() => toggle(o.geo)}
                        disabled={full}
                        aria-pressed={slot !== -1}
                        title={full ? "Up to two origins at a time" : undefined}
                        className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs disabled:opacity-40 ${slot !== -1 ? "border-foreground/20 bg-background font-medium" : "border-border text-muted hover:text-foreground"}`}
                      >
                        {slot !== -1 && <span aria-hidden className="size-2 rounded-full" style={{ background: SERIES_COLORS[slot + 1] }} />}
                        {o.label}
                      </button>
                    );
                  })}
                </div>
              }
              table={<SeriesTable series={lineSeries} valueFormat={eurKg} />}
              caption={
                <>
                  Monthly customs unit value = declared value ÷ declared quantity. Only validated months are plotted: months under 50 t
                  of imports, or more than 3× away from the series median, are excluded. Source: Eurostat Comext DS-045409.
                </>
              }
            >
              <TimeLineChart series={lineSeries} valueFormat={eurKg} />
            </ChartFrame>

            <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
              <ChartFrame
                title="Extra-EU import volume (tonnes)"
                table={
                  <SeriesTable
                    series={[{ key: "v", label: "Tonnes", color: SERIES_COLORS[0], points: volumePoints }]}
                    valueFormat={(v) => Math.round(v).toLocaleString("en-GB")}
                  />
                }
              >
                <TimeBarChart points={volumePoints} label="Imports" valueFormat={(v) => `${Math.round(v).toLocaleString("en-GB")} t`} />
              </ChartFrame>

              <Card title={`Origins · ${fmtMonth(overview.latest_month, "long")}`}>
                {overview.origins.length === 0 ? (
                  <EmptyState title="No origin data for this month" />
                ) : (
                  <div className="-mx-5 overflow-x-auto">
                    <table className="w-full min-w-[480px] text-sm">
                      <thead>
                        <tr className="border-b border-border text-left text-xs text-muted">
                          <th className="px-5 py-2 font-medium">Origin</th>
                          <th className="px-3 py-2 text-right font-medium">EUR/kg</th>
                          <th className="px-3 py-2 text-right font-medium">vs prev.</th>
                          <th className="px-3 py-2 text-right font-medium">Volume</th>
                          <th className="px-3 py-2 text-right font-medium">Share</th>
                          <th className="px-5 py-2 font-medium">Quality</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border tabular-nums">
                        {overview.origins.map((o) => (
                          <tr key={o.geography}>
                            <td className="px-5 py-2">{o.label}</td>
                            <td className="px-3 py-2 text-right">{o.unit_value ? fmtNumber(o.unit_value) : "—"}</td>
                            <td className="px-3 py-2 text-right">{fmtPct(o.mom_pct)}</td>
                            <td className="px-3 py-2 text-right">{fmtTonnes(o.quantity_kg)}</td>
                            <td className="px-3 py-2 text-right">{o.volume_share_pct ? `${fmtNumber(o.volume_share_pct, 0)}%` : "—"}</td>
                            <td className="px-5 py-2"><QualityBadge q={o.unit_value_quality} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>
            </div>
          </>
        )}

        {overview && (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <Card title="Market drivers">
              <EmptyState title="Not available yet">
                Production and climate indicators (FAOSTAT, Copernicus) and AI-written driver summaries based only on stored data arrive in later sprints.
              </EmptyState>
            </Card>
            <Card title="Sources">
              {overview.sources.length === 0 ? (
                <EmptyState title="No sources loaded yet" />
              ) : (
                <ul className="space-y-4">
                  {overview.sources.map((s) => (
                    <li key={s.id} className="text-sm">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{s.name}</span>
                        <Badge>{s.source_type.replace("_", " ")}</Badge>
                        {s.is_synthetic && <Badge tone="warning">synthetic</Badge>}
                        {s.last_run_status === "failed" && <Badge tone="negative">last run failed</Badge>}
                      </div>
                      <dl className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 text-xs text-muted">
                        <dt>Latest period</dt>
                        <dd className="text-foreground">{fmtMonth(s.latest_observation_date, "long")}</dd>
                        <dt>Last updated</dt>
                        <dd className="text-foreground">{fmtDateTime(s.last_success_at ?? s.last_collected_at)}</dd>
                        <dt>Observations</dt>
                        <dd className="text-foreground">{s.observations.toLocaleString("en-GB")}</dd>
                        <dt>Frequency</dt>
                        <dd className="text-foreground">{s.update_frequency ?? "—"}</dd>
                        {s.last_data_version && (
                          <>
                            <dt>Data version</dt>
                            <dd className="font-mono text-foreground" title={s.last_data_version}>{s.last_data_version.slice(0, 12)}</dd>
                          </>
                        )}
                        {s.license_reference && (
                          <>
                            <dt>Licence</dt>
                            <dd>{s.license_reference}</dd>
                          </>
                        )}
                      </dl>
                      {s.last_run_status === "failed" && s.last_error && me.is_platform_admin && (
                        <p className="mt-1 text-xs text-negative">{s.last_error}</p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        )}
        {!overview && !error && <div className="h-64 animate-pulse rounded-lg border border-border bg-surface" />}
      </div>
    </>
  );
}
