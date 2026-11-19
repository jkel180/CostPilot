const num = (v: string | number | null | undefined) => (v === null || v === undefined || v === "" ? null : Number(v));

export function fmtNumber(v: string | number | null | undefined, digits = 2): string {
  const n = num(v);
  return n === null || Number.isNaN(n) ? "—" : n.toLocaleString("en-GB", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function fmtInt(v: string | number | null | undefined): string {
  const n = num(v);
  return n === null || Number.isNaN(n) ? "—" : Math.round(n).toLocaleString("en-GB");
}

export function fmtPct(v: string | number | null | undefined, digits = 1): string {
  const n = num(v);
  if (n === null || Number.isNaN(n)) return "—";
  return `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n).toFixed(digits)}%`;
}

/** kg -> tonnes, no decimals */
export function fmtTonnes(kg: string | number | null | undefined): string {
  const n = num(kg);
  return n === null || Number.isNaN(n) ? "—" : `${Math.round(n / 1000).toLocaleString("en-GB")} t`;
}

export function fmtMonth(iso: string | null | undefined, style: "short" | "long" = "short"): string {
  if (!iso) return "—";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return d.toLocaleDateString("en-GB", { month: style === "short" ? "short" : "long", year: style === "short" ? "2-digit" : "numeric", timeZone: "UTC" });
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
