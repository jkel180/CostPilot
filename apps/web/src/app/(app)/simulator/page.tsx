"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "@/components/app-shell";
import { ChartFrame } from "@/components/charts";
import { ImpactBars } from "@/components/forecast-charts";
import { useOrg } from "@/components/org-context";
import { Alert, Badge, Button, Card, EmptyState, Field, Input, Select } from "@/components/ui";
import { fmtDateTime, fmtMonth, fmtNumber, fmtPct } from "@/lib/format";
import type { CostModel, SimulationResult } from "@/lib/types";

const CURRENCIES = ["EUR", "USD", "GBP", "CHF"];
const UNITS = ["kg", "t", "lb", "l"];

function money(v: string | number | null | undefined, ccy: string) {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  return `${n < 0 ? "−" : n > 0 ? "+" : ""}${Math.abs(n).toLocaleString("en-GB", { maximumFractionDigits: 0 })} ${ccy}`;
}

function CostModelForm({ model, canEdit, onSaved }: { model: CostModel | null; canEdit: boolean; onSaved: () => void }) {
  const { api } = useOrg();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const num = (k: string) => (String(f.get(k) ?? "").trim().replace(",", ".") || null);
    setBusy(true);
    setError(null);
    try {
      await api("/cost-model", {
        method: "PUT",
        body: {
          name: "Lemon juice concentrate",
          expected_volume: num("expected_volume"),
          volume_period: f.get("volume_period"),
          current_purchase_price: num("current_purchase_price"),
          target_purchase_price: num("target_purchase_price"),
          currency: f.get("currency"),
          unit: f.get("unit"),
          pass_through_pct: num("pass_through_pct") ?? "100",
          commodity_cost_share_pct: num("commodity_cost_share_pct"),
          notes: String(f.get("notes") ?? "").trim() || null,
        },
      });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Your cost model"
      action={
        <span className="flex items-center gap-2">
          <Badge tone="warning">your assumptions</Badge>
          {model && <span className="text-xs text-muted">saved {fmtDateTime(model.updated_at)}</span>}
        </span>
      }
    >
      <form onSubmit={save} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <fieldset disabled={!canEdit || busy} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Expected volume">
            <Input name="expected_volume" inputMode="decimal" required defaultValue={model ? Number(model.expected_volume) : ""} placeholder="120000" />
          </Field>
          <Field label="Per">
            <Select name="volume_period" defaultValue={model?.volume_period ?? "annual"}>
              <option value="annual">Year</option>
              <option value="monthly">Month</option>
            </Select>
          </Field>
          <Field label="Unit">
            <Select name="unit" defaultValue={model?.unit ?? "kg"}>
              {UNITS.map((u) => <option key={u}>{u}</option>)}
            </Select>
          </Field>
          <Field label="Currency">
            <Select name="currency" defaultValue={model?.currency ?? "EUR"}>
              {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
            </Select>
          </Field>
          <Field label="Current purchase price" hint="per unit above">
            <Input name="current_purchase_price" inputMode="decimal" required defaultValue={model ? Number(model.current_purchase_price) : ""} placeholder="2.50" />
          </Field>
          <Field label="Target price" hint="optional">
            <Input name="target_purchase_price" inputMode="decimal" defaultValue={model?.target_purchase_price ? Number(model.target_purchase_price) : ""} />
          </Field>
          <Field label="Pass-through %" hint="share of a benchmark change reaching your price">
            <Input name="pass_through_pct" inputMode="decimal" defaultValue={model ? Number(model.pass_through_pct) : 100} />
          </Field>
          <Field label="Cost share %" hint="optional: share of product cost">
            <Input name="commodity_cost_share_pct" inputMode="decimal" defaultValue={model?.commodity_cost_share_pct ? Number(model.commodity_cost_share_pct) : ""} />
          </Field>
          <div className="sm:col-span-2 lg:col-span-4">
            <Field label="Notes" hint="optional: contract terms, assumptions">
              <Input name="notes" maxLength={2000} defaultValue={model?.notes ?? ""} />
            </Field>
          </div>
        </fieldset>
        {canEdit ? (
          <Button type="submit" disabled={busy}>{busy ? "Saving…" : model ? "Save changes" : "Save cost model"}</Button>
        ) : (
          <p className="text-xs text-muted">Only admins and analysts can change the cost model.</p>
        )}
      </form>
    </Card>
  );
}

export default function SimulatorPage() {
  const { api, role, current } = useOrg();
  const canEdit = role !== "viewer";
  const [model, setModel] = useState<CostModel | null | undefined>(undefined);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [months, setMonths] = useState(3);
  const [custom, setCustom] = useState(["-10", "10", ""]);
  const [error, setError] = useState<string | null>(null);
  const [formKey, setFormKey] = useState(0);

  const loadModel = useCallback(async () => {
    try {
      setModel(await api<CostModel | null>("/cost-model"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the cost model");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current.organization_id]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial data load
    void loadModel();
  }, [loadModel]);

  useEffect(() => {
    if (!model) return;
    const changes = custom.map((c) => c.trim().replace(",", ".")).filter((c) => c !== "" && !Number.isNaN(Number(c)));
    const t = setTimeout(() => {
      api<SimulationResult>("/simulator", { method: "POST", body: { months, custom_changes_pct: changes } })
        .then((r) => {
          setResult(r);
          setError(null);
        })
        .catch((e: Error) => setError(e.message));
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model, months, custom]);

  const ccy = result?.currency ?? model?.currency ?? "EUR";

  return (
    <>
      <PageHeader title="Cost Simulator" description="What market scenarios mean for your purchasing budget." />
      <div className="space-y-4">
        {error && <Alert>{error}</Alert>}
        {model !== undefined && (
          <CostModelForm key={formKey} model={model} canEdit={canEdit} onSaved={() => { setFormKey((k) => k + 1); void loadModel(); }} />
        )}
        {model === null && (
          <Card><EmptyState title="Save your cost model to see scenarios">Volumes and current price stay private to your organization.</EmptyState></Card>
        )}

        {model && result && (
          <>
            <Card
              title="Scenarios"
              action={
                <div className="flex flex-wrap items-center gap-3 text-xs">
                  <label className="flex items-center gap-1.5 text-muted">
                    Period
                    <Select value={months} onChange={(e) => setMonths(Number(e.target.value))} className="h-8 w-28">
                      {[1, 3, 6, 12].map((m) => <option key={m} value={m}>{m} month{m > 1 ? "s" : ""}</option>)}
                    </Select>
                  </label>
                  <span className="flex items-center gap-1.5 text-muted">
                    Custom changes %
                    {custom.map((c, i) => (
                      <Input
                        key={i}
                        value={c}
                        inputMode="decimal"
                        aria-label={`Custom benchmark change ${i + 1}`}
                        onChange={(e) => setCustom(custom.map((x, j) => (j === i ? e.target.value : x)))}
                        className="h-8 w-16"
                        placeholder="+5"
                      />
                    ))}
                  </span>
                </div>
              }
            >
              <div className="space-y-4">
                <div className="grid gap-3 text-sm sm:grid-cols-3">
                  <div className="rounded-md bg-background px-3 py-2">
                    <p className="text-xs text-muted">Your volume <Badge tone="warning">assumption</Badge></p>
                    <p className="mt-1 font-medium tabular-nums">{fmtNumber(result.monthly_quantity, 0)} {result.unit}/month · {fmtNumber(Number(result.monthly_quantity) * months, 0)} {result.unit} in {months} months</p>
                  </div>
                  <div className="rounded-md bg-background px-3 py-2">
                    <p className="text-xs text-muted">Your price vs benchmark <Badge>observed</Badge></p>
                    {result.market_gap.available ? (
                      <p className="mt-1 font-medium tabular-nums">
                        {fmtPct(result.market_gap.gap_pct)} <span className="font-normal text-muted">({fmtNumber(result.market_gap.customer_price_per_kg)} vs €{fmtNumber(result.market_gap.benchmark_per_kg)}/kg, {fmtMonth(result.market_gap.benchmark_date)})</span>
                      </p>
                    ) : (
                      <p className="mt-1 text-xs text-muted">Not comparable: {result.market_gap.rule}</p>
                    )}
                  </div>
                  <div className="rounded-md bg-background px-3 py-2">
                    <p className="text-xs text-muted">Reaching your target price <Badge tone="positive">calculated</Badge></p>
                    <p className="mt-1 font-medium tabular-nums">
                      {result.target_annual_savings === null ? "Set a target price" : `${money(-Number(result.target_annual_savings), ccy).replace("+", "")} per year`}
                    </p>
                  </div>
                </div>
                {result.forecast_note && <Alert tone="warning">{result.forecast_note}</Alert>}

                <div className="-mx-5 overflow-x-auto">
                  <table className="w-full min-w-[860px] text-sm">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted">
                        <th className="px-5 py-2 font-medium">Scenario</th>
                        <th className="px-3 py-2 text-right font-medium">Benchmark</th>
                        <th className="px-3 py-2 text-right font-medium">Your price</th>
                        <th className="px-3 py-2 text-right font-medium">Price ({ccy}/{result.unit})</th>
                        <th className="px-3 py-2 text-right font-medium">Spend, {months}M</th>
                        <th className="px-3 py-2 text-right font-medium">Impact, {months}M</th>
                        <th className="px-5 py-2 text-right font-medium">Annualized</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border tabular-nums">
                      <tr className="text-muted">
                        <td className="px-5 py-2">Current price (no change)</td>
                        <td className="px-3 py-2 text-right">—</td>
                        <td className="px-3 py-2 text-right">—</td>
                        <td className="px-3 py-2 text-right">{fmtNumber(result.inputs.current_purchase_price, 2)}</td>
                        <td className="px-3 py-2 text-right">{fmtNumber(result.scenarios[0]?.baseline_spend, 0)}</td>
                        <td className="px-3 py-2 text-right">0</td>
                        <td className="px-5 py-2 text-right">0</td>
                      </tr>
                      {result.scenarios.map((s) => (
                        <tr key={s.key} title={s.assumption}>
                          <td className="px-5 py-2">
                            {s.label}{" "}
                            <Badge tone={s.source === "forecast" ? "accent" : "warning"}>{s.source === "forecast" ? "forecast" : "assumption"}</Badge>
                            {s.source === "forecast" && s.forecast_quality !== "reliable" && <span className="ml-1"><Badge tone="warning">below baseline</Badge></span>}
                            <p className="mt-0.5 text-[11px] text-subtle">{s.assumption}</p>
                          </td>
                          <td className="px-3 py-2 text-right">{fmtPct(s.benchmark_change_pct)}</td>
                          <td className="px-3 py-2 text-right">{fmtPct(s.price_change_pct)}</td>
                          <td className="px-3 py-2 text-right">{fmtNumber(s.scenario_price, 2)}</td>
                          <td className="px-3 py-2 text-right">{fmtNumber(s.expected_spend, 0)}</td>
                          <td className={`px-3 py-2 text-right font-medium ${Number(s.period_impact) > 0 ? "text-negative" : Number(s.period_impact) < 0 ? "text-accent" : ""}`}>{money(s.period_impact, ccy)}</td>
                          <td className="px-5 py-2 text-right">{money(s.annualized_impact, ccy)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </Card>

            {result.scenarios.length > 0 && (
              <ChartFrame
                title={`Cost impact over ${months} month${months > 1 ? "s" : ""} (${ccy})`}
                table={
                  <table className="w-full text-xs">
                    <tbody className="divide-y divide-border tabular-nums">
                      {result.scenarios.map((s) => (
                        <tr key={s.key}><td className="py-1.5 pr-3">{s.label}</td><td className="py-1.5 text-right">{money(s.period_impact, ccy)}</td></tr>
                      ))}
                    </tbody>
                  </table>
                }
                caption="Impact = (scenario price − current price) × your quantity over the period. Positive = extra cost, negative = saving. Annualized = monthly impact × 12."
              >
                <ImpactBars
                  items={result.scenarios.map((s) => ({ label: s.label, value: Number(s.period_impact), note: s.assumption }))}
                  valueFormat={(v) => money(v, ccy)}
                />
              </ChartFrame>
            )}
          </>
        )}
        {model === undefined && !error && <div className="h-48 animate-pulse rounded-lg border border-border bg-surface" />}
      </div>
    </>
  );
}
