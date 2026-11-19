"use client";

import { useState, type FormEvent } from "react";
import { Alert, Button, Field, Input, Select } from "@/components/ui";

export const CURRENCIES = ["EUR", "USD", "GBP", "CHF"] as const;

export type OrgFormValues = { name: string; country: string | null; currency: string };

/** Shared by registration and the Settings profile. */
export function OrgForm({
  initial,
  submitLabel,
  disabled,
  onSubmit,
}: {
  initial?: Partial<OrgFormValues>;
  submitLabel: string;
  disabled?: boolean;
  onSubmit: (values: OrgFormValues) => Promise<void>;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handle(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const country = String(f.get("country") ?? "").trim().toUpperCase();
    setBusy(true);
    setError(null);
    try {
      await onSubmit({ name: String(f.get("name")).trim(), country: country || null, currency: String(f.get("currency")) });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handle} className="space-y-4">
      {error && <Alert>{error}</Alert>}
      <Field label="Organization name">
        <Input name="name" defaultValue={initial?.name} minLength={2} maxLength={200} required disabled={disabled} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Country" hint="ISO code, e.g. IT">
          <Input
            name="country"
            defaultValue={initial?.country ?? ""}
            maxLength={2}
            pattern="[A-Za-z]{2}"
            placeholder="IT"
            disabled={disabled}
          />
        </Field>
        <Field label="Reporting currency">
          <Select name="currency" defaultValue={initial?.currency ?? "EUR"} disabled={disabled}>
            {CURRENCIES.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </Select>
        </Field>
      </div>
      {!disabled && (
        <Button type="submit" disabled={busy}>
          {busy ? "Saving…" : submitLabel}
        </Button>
      )}
    </form>
  );
}
