"use client";

import { useState } from "react";
import { useOrg } from "@/components/org-context";
import { Alert, Badge, Button, Card, Select } from "@/components/ui";
import type { ImportPreview, PurchaseImport } from "@/lib/types";

const LABELS: Record<string, string> = {
  purchase_date: "Purchase date",
  supplier: "Supplier",
  product_description: "Product description",
  quantity: "Quantity",
  unit: "Unit of measure",
  unit_price: "Unit price",
  currency: "Currency",
  brix: "Brix",
  country_of_origin: "Country of origin",
  quality_grade: "Quality grade",
  incoterm: "Incoterm",
  delivery_location: "Delivery location",
  contract_type: "Contract type",
  packaging: "Packaging",
  certification: "Certification",
};

/** Upload -> preview (nothing stored) -> adjust mapping -> import. */
export function PurchaseImportFlow({ onImported }: { onImported: () => void }) {
  const { api } = useOrg();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  function form(extra: Record<string, string> = {}) {
    const fd = new FormData();
    fd.append("file", file!);
    fd.append("mapping", JSON.stringify(mapping));
    Object.entries(extra).forEach(([k, v]) => fd.append(k, v));
    return fd;
  }

  async function runPreview(f: File, m: Record<string, string | null>) {
    setBusy(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", f);
      if (Object.keys(m).length) fd.append("mapping", JSON.stringify(m));
      const p = await api<ImportPreview>("/purchases/imports/preview", { method: "POST", body: fd });
      setPreview(p);
      setMapping(p.mapping);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not read the file");
      setPreview(null);
    } finally {
      setBusy(false);
    }
  }

  async function commit(skipInvalid: boolean) {
    setBusy(true);
    setError(null);
    try {
      const r = await api<PurchaseImport>("/purchases/imports", { method: "POST", body: form({ skip_invalid: String(skipInvalid) }) });
      setDone(`${r.rows_imported} purchases imported from ${r.filename}${r.rows_skipped ? `, ${r.rows_skipped} rows skipped` : ""}.`);
      reset(false);
      onImported();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  function reset(clearDone = true) {
    setFile(null);
    setPreview(null);
    setMapping({});
    if (clearDone) setDone(null);
  }

  const fields = preview ? [...preview.required_fields, ...preview.optional_fields] : [];
  const shownFields = preview ? fields.filter((f) => preview.preview.some((r) => r.values?.[f])) : [];

  return (
    <Card title="Upload purchases (CSV)" action={preview && <Button variant="ghost" onClick={() => reset()}>Cancel</Button>}>
      <div className="space-y-4">
        {done && <Alert tone="positive">{done}</Alert>}
        {error && <Alert>{error}</Alert>}

        {!preview && (
          <div className="space-y-3">
            <label className="flex cursor-pointer flex-col items-center justify-center rounded-md border border-dashed border-border px-6 py-8 text-center hover:bg-background">
              <span className="text-sm font-medium">{busy ? "Reading file…" : "Choose a CSV file"}</span>
              <span className="mt-1 text-xs text-muted">Exported from Excel or your ERP · max 5 MB · comma or semicolon separated</span>
              <input
                type="file"
                accept=".csv,text/csv"
                className="sr-only"
                disabled={busy}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  e.target.value = "";
                  if (f) {
                    setDone(null);
                    setFile(f);
                    void runPreview(f, {});
                  }
                }}
              />
            </label>
            <p className="text-xs leading-relaxed text-muted">
              Required columns: purchase date, supplier, product description, quantity, unit of measure, unit price, currency.
              Optional: Brix, country of origin, quality grade, Incoterm, delivery location, contract type, packaging, certification.
              Italian or English column names are recognised; you can fix the mapping in the next step. Nothing is saved until you confirm.
            </p>
          </div>
        )}

        {preview && (
          <>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium">{preview.filename}</span>
              <Badge>{preview.rows_total} rows</Badge>
              <Badge tone="positive">{preview.rows_valid} valid</Badge>
              {preview.rows_invalid > 0 && <Badge tone="negative">{preview.rows_invalid} with errors</Badge>}
              <span className="text-xs text-muted">
                Separator “{preview.delimiter === "\t" ? "tab" : preview.delimiter}” · numbers read as {preview.number_format}
              </span>
            </div>

            <details open={preview.mapping_errors.length > 0} className="rounded-md border border-border">
              <summary className="cursor-pointer px-3 py-2 text-sm font-medium">Column mapping</summary>
              <div className="grid gap-2 border-t border-border p-3 sm:grid-cols-2 lg:grid-cols-3">
                {fields.map((f) => (
                  <label key={f} className="text-xs">
                    <span className="mb-1 block text-muted">
                      {LABELS[f] ?? f}
                      {preview.required_fields.includes(f) && <span className="text-negative"> *</span>}
                    </span>
                    <Select
                      value={mapping[f] ?? ""}
                      onChange={(e) => setMapping({ ...mapping, [f]: e.target.value || null })}
                      className="h-8"
                    >
                      <option value="">— not in file —</option>
                      {preview.columns.filter(Boolean).map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </Select>
                  </label>
                ))}
                <div className="sm:col-span-2 lg:col-span-3">
                  <Button variant="secondary" disabled={busy} onClick={() => runPreview(file!, mapping)}>
                    Apply mapping
                  </Button>
                </div>
              </div>
            </details>

            {preview.mapping_errors.length > 0 && (
              <Alert>
                <ul className="list-inside list-disc">
                  {preview.mapping_errors.map((m) => <li key={m}>{m}</li>)}
                </ul>
              </Alert>
            )}

            {preview.preview.length > 0 && (
              <div>
                <p className="mb-2 text-xs font-medium text-muted">Preview (first {preview.preview.length} rows, as they will be stored)</p>
                <div className="max-h-72 overflow-auto rounded-md border border-border">
                  <table className="w-full min-w-[720px] text-xs">
                    <thead className="sticky top-0 bg-background">
                      <tr className="text-left text-muted">
                        <th className="px-2 py-1.5 font-medium">Line</th>
                        {shownFields.map((f) => <th key={f} className="px-2 py-1.5 font-medium">{LABELS[f] ?? f}</th>)}
                        <th className="px-2 py-1.5 font-medium">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border tabular-nums">
                      {preview.preview.map((r) => (
                        <tr key={r.line} className={r.errors.length ? "bg-negative-soft/50" : ""}>
                          <td className="px-2 py-1.5 text-muted">{r.line}</td>
                          {shownFields.map((f) => <td key={f} className="px-2 py-1.5">{r.values?.[f] ?? ""}</td>)}
                          <td className="px-2 py-1.5">{r.errors.length ? <span className="text-negative">{r.errors.join("; ")}</span> : "OK"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {preview.errors.length > 0 && (
              <details className="rounded-md border border-border">
                <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-negative">
                  {preview.rows_invalid} rows with errors{preview.rows_invalid > preview.errors.length ? ` (first ${preview.errors.length} shown)` : ""}
                </summary>
                <ul className="max-h-48 space-y-1 overflow-auto border-t border-border p-3 text-xs">
                  {preview.errors.map((r) => (
                    <li key={r.line}><span className="font-medium">Line {r.line}:</span> {r.errors.join("; ")}</li>
                  ))}
                </ul>
              </details>
            )}

            {preview.mapping_errors.length === 0 && preview.rows_valid > 0 && (
              <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
                {preview.rows_invalid === 0 ? (
                  <Button disabled={busy} onClick={() => commit(false)}>Import {preview.rows_valid} purchases</Button>
                ) : (
                  <>
                    <Button disabled={busy} onClick={() => commit(true)}>Import {preview.rows_valid} valid rows, skip {preview.rows_invalid}</Button>
                    <span className="text-xs text-muted">Or fix the file and upload it again.</span>
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </Card>
  );
}
