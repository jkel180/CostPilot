"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/app-shell";
import { ChartFrame, SERIES_COLORS, SeriesTable, TimeLineChart } from "@/components/charts";
import { useOrg } from "@/components/org-context";
import { PurchaseImportFlow } from "@/components/purchase-import";
import { Alert, Badge, Button, Card, EmptyState, Select } from "@/components/ui";
import { fmtDate, fmtDateTime, fmtNumber } from "@/lib/format";
import type { Purchase, PurchaseAnalysis, PurchaseImport, WappGroup } from "@/lib/types";

const groupKey = (g: WappGroup) => `${g.unit}|${g.currency}`;

export default function PurchasesPage() {
  const { api, role, current } = useOrg();
  const canEdit = role !== "viewer";
  const [analysis, setAnalysis] = useState<PurchaseAnalysis | null>(null);
  const [purchases, setPurchases] = useState<{ total: number; items: Purchase[] } | null>(null);
  const [imports, setImports] = useState<PurchaseImport[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [unitGroup, setUnitGroup] = useState<string>("");

  const load = useCallback(async () => {
    try {
      const [a, p, i] = await Promise.all([
        api<PurchaseAnalysis>("/purchases/analysis"),
        api<{ total: number; items: Purchase[] }>("/purchases?limit=200"),
        api<PurchaseImport[]>("/purchases/imports"),
      ]);
      setAnalysis(a);
      setPurchases(p);
      setImports(i);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load purchases");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current.organization_id]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial data load
    void load();
  }, [load]);

  // charts and averages never mix units or currencies: the user picks one group
  const groups = analysis?.overall ?? [];
  const selected = unitGroup || (groups[0] ? groupKey(groups[0]) : "");
  const sel = groups.find((g) => groupKey(g) === selected);

  const monthly = useMemo(
    () =>
      (analysis?.by_month ?? [])
        .filter((g) => groupKey(g) === selected && g.weighted_avg_price)
        .map((g) => ({ date: `${g.key}-01`, value: Number(g.weighted_avg_price) })),
    [analysis, selected],
  );
  const suppliers = (analysis?.by_supplier ?? []).filter((g) => groupKey(g) === selected);
  const products = (analysis?.by_product ?? []).filter((g) => groupKey(g) === selected);
  const priceFmt = (v: number) => `${fmtNumber(v)} ${sel?.currency ?? ""}`;

  async function removeImport(i: PurchaseImport) {
    if (!window.confirm(`Delete the import “${i.filename}” and its ${i.rows_imported} purchases?`)) return;
    try {
      await api(`/purchases/imports/${i.id}`, { method: "DELETE" });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete the import");
    }
  }

  const empty = purchases && purchases.total === 0;

  return (
    <>
      <PageHeader
        title="My Purchases"
        description="Your purchase history for lemon juice concentrate. Visible only to your organization."
        actions={
          groups.length > 1 ? (
            <label className="flex items-center gap-2 text-xs text-muted">
              Unit / currency
              <Select value={selected} onChange={(e) => setUnitGroup(e.target.value)} className="h-8 w-32">
                {groups.map((g) => (
                  <option key={groupKey(g)} value={groupKey(g)}>{g.currency}/{g.unit}</option>
                ))}
              </Select>
            </label>
          ) : undefined
        }
      />
      <div className="space-y-4">
        {error && <Alert>{error}</Alert>}
        {canEdit && <PurchaseImportFlow onImported={load} />}
        {!canEdit && empty && (
          <Card><EmptyState title="No purchases yet">An admin or analyst of your organization can upload them.</EmptyState></Card>
        )}

        {sel && (
          <section aria-label="Summary" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {[
              { label: "Weighted average price", value: `${fmtNumber(sel.weighted_avg_price)} ${sel.currency}/${sel.unit}`, sub: "Σ(qty × price) ÷ Σ qty" },
              { label: "Total quantity", value: `${fmtNumber(sel.total_quantity, 0)} ${sel.unit}`, sub: `${sel.purchases} purchases` },
              { label: "Total spend", value: `${fmtNumber(sel.total_spend, 0)} ${sel.currency}` },
              { label: "Price range", value: `${fmtNumber(sel.min_price)} – ${fmtNumber(sel.max_price)}`, sub: `${fmtDate(sel.first_purchase)} – ${fmtDate(sel.last_purchase)}` },
            ].map((t) => (
              <div key={t.label} className="rounded-lg border border-border bg-surface p-4">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-xs font-medium text-muted">{t.label}</p>
                  <Badge tone="positive">calculated</Badge>
                </div>
                <p className="mt-2 text-xl font-semibold tracking-tight tabular-nums">{t.value}</p>
                {t.sub && <p className="mt-1 text-[11px] text-subtle">{t.sub}</p>}
              </div>
            ))}
          </section>
        )}

        {sel && monthly.length > 0 && (
          <ChartFrame
            title={`Price evolution (${sel.currency}/${sel.unit}, monthly weighted average)`}
            table={<SeriesTable series={[{ key: "p", label: "Weighted avg.", color: SERIES_COLORS[0], points: monthly }]} valueFormat={priceFmt} />}
            caption="Each point is the weighted average of that month's purchases in this unit and currency. Months without purchases are gaps."
          >
            <TimeLineChart series={[{ key: "p", label: "Weighted average price", color: SERIES_COLORS[0], points: monthly }]} valueFormat={priceFmt} />
          </ChartFrame>
        )}

        {sel && (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {[
              { title: "Supplier analysis", rows: suppliers, col: "Supplier" },
              { title: "By product specification", rows: products, col: "Product description" },
            ].map((block) => (
              <Card key={block.title} title={block.title}>
                <div className="-mx-5 overflow-x-auto">
                  <table className="w-full min-w-[520px] text-sm">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted">
                        <th className="px-5 py-2 font-medium">{block.col}</th>
                        <th className="px-3 py-2 text-right font-medium">Purchases</th>
                        <th className="px-3 py-2 text-right font-medium">Quantity ({sel.unit})</th>
                        <th className="px-3 py-2 text-right font-medium">Wtd. avg ({sel.currency})</th>
                        <th className="px-5 py-2 text-right font-medium">Min – max</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border tabular-nums">
                      {block.rows.map((g) => (
                        <tr key={g.key}>
                          <td className="max-w-56 truncate px-5 py-2" title={g.key}>{g.key}</td>
                          <td className="px-3 py-2 text-right">{g.purchases}</td>
                          <td className="px-3 py-2 text-right">{fmtNumber(g.total_quantity, 0)}</td>
                          <td className="px-3 py-2 text-right font-medium">{fmtNumber(g.weighted_avg_price)}</td>
                          <td className="px-5 py-2 text-right text-muted">{fmtNumber(g.min_price)} – {fmtNumber(g.max_price)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            ))}
          </div>
        )}

        {purchases && purchases.total > 0 && (
          <Card title="Purchase history" action={<span className="text-xs text-muted">{purchases.total} purchases{purchases.total > purchases.items.length ? ` · latest ${purchases.items.length} shown` : ""}</span>}>
            <div className="-mx-5 max-h-[420px] overflow-auto">
              <table className="w-full min-w-[820px] text-sm">
                <thead className="sticky top-0 bg-surface">
                  <tr className="border-b border-border text-left text-xs text-muted">
                    <th className="px-5 py-2 font-medium">Date</th>
                    <th className="px-3 py-2 font-medium">Supplier</th>
                    <th className="px-3 py-2 font-medium">Product</th>
                    <th className="px-3 py-2 text-right font-medium">Quantity</th>
                    <th className="px-3 py-2 text-right font-medium">Unit price</th>
                    <th className="px-3 py-2 font-medium">Brix</th>
                    <th className="px-3 py-2 font-medium">Origin</th>
                    <th className="px-5 py-2 font-medium">Incoterm</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border tabular-nums">
                  {purchases.items.map((p) => (
                    <tr key={p.id}>
                      <td className="whitespace-nowrap px-5 py-2">{fmtDate(p.purchase_date)}</td>
                      <td className="px-3 py-2">{p.supplier}</td>
                      <td className="max-w-56 truncate px-3 py-2" title={p.product_description}>{p.product_description}</td>
                      <td className="whitespace-nowrap px-3 py-2 text-right">{fmtNumber(p.quantity, 0)} {p.unit}</td>
                      <td className="whitespace-nowrap px-3 py-2 text-right">{fmtNumber(p.unit_price)} {p.currency}</td>
                      <td className="px-3 py-2">{p.brix ? fmtNumber(p.brix, 0) : "—"}</td>
                      <td className="px-3 py-2">{p.country_of_origin ?? "—"}</td>
                      <td className="px-5 py-2">{p.incoterm ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}

        {imports && imports.length > 0 && (
          <Card title="Uploads">
            <ul className="divide-y divide-border text-sm">
              {imports.map((i) => (
                <li key={i.id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                  <div>
                    <p className="font-medium">{i.filename}</p>
                    <p className="text-xs text-muted">
                      {fmtDateTime(i.created_at)} · {i.rows_imported} imported{i.rows_skipped ? ` · ${i.rows_skipped} skipped` : ""}
                    </p>
                  </div>
                  {canEdit && <Button variant="danger" className="h-8" onClick={() => removeImport(i)}>Delete</Button>}
                </li>
              ))}
            </ul>
          </Card>
        )}
        {!purchases && !error && <div className="h-40 animate-pulse rounded-lg border border-border bg-surface" />}
      </div>
    </>
  );
}
