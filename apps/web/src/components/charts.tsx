"use client";

import { useState, type ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
  type TooltipValueType as ValueType,
} from "recharts";
import type { NameType } from "recharts/types/component/DefaultTooltipContent";
import { fmtMonth } from "@/lib/format";

/**
 * Validated categorical palette (light surface), first three slots only: they pass the
 * colour-vision checks for every pair. Charts here never show more than three series.
 */
export const SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a"] as const;

const AXIS = { fontSize: 11, fill: "var(--muted)" };
const GRID = "#eceef2";

export type LineSeries = { key: string; label: string; color: string; points: { date: string; value: number }[] };

type Row = { date: string } & Record<string, number | string | undefined>;

function mergeByDate(series: LineSeries[]): Row[] {
  const rows = new Map<string, Row>();
  for (const s of series) {
    for (const p of s.points) {
      const row = rows.get(p.date) ?? { date: p.date };
      row[s.key] = p.value;
      rows.set(p.date, row);
    }
  }
  return [...rows.values()].sort((a, b) => a.date.localeCompare(b.date));
}

function TooltipBox({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="min-w-40 rounded-md border border-border bg-surface px-3 py-2 text-xs shadow-[0_4px_12px_rgba(11,27,51,0.08)]">
      <p className="mb-1.5 font-medium text-foreground">{title}</p>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function Swatch({ color, shape = "line" }: { color: string; shape?: "line" | "square" }) {
  return shape === "line" ? (
    <span aria-hidden className="inline-block h-0.5 w-3 rounded-full" style={{ background: color }} />
  ) : (
    <span aria-hidden className="inline-block size-2.5 rounded-sm" style={{ background: color }} />
  );
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  if (items.length < 2) return null;
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted" aria-label="Legend">
      {items.map((i) => (
        <li key={i.label} className="inline-flex items-center gap-1.5">
          <Swatch color={i.color} />
          {i.label}
        </li>
      ))}
    </ul>
  );
}

/** Chart with a "Table" toggle so values are never available only as colour/position. */
export function ChartFrame({
  title,
  caption,
  table,
  controls,
  children,
}: {
  title: string;
  caption?: ReactNode;
  table: ReactNode;
  controls?: ReactNode;
  children: ReactNode;
}) {
  const [view, setView] = useState<"chart" | "table">("chart");
  return (
    <section className="rounded-lg border border-border bg-surface">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3.5">
        <h2 className="text-sm font-semibold">{title}</h2>
        <div className="flex items-center gap-2">
          {controls}
          <div className="inline-flex rounded-md border border-border p-0.5 text-xs" role="group" aria-label="View">
            {(["chart", "table"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                aria-pressed={view === v}
                className={`rounded px-2 py-1 capitalize ${view === v ? "bg-accent-soft font-medium text-accent" : "text-muted hover:text-foreground"}`}
              >
                {v}
              </button>
            ))}
          </div>
        </div>
      </header>
      <div className="p-5">
        {view === "chart" ? children : <div className="max-h-72 overflow-auto">{table}</div>}
        {caption && <div className="mt-3 text-[11px] leading-relaxed text-subtle">{caption}</div>}
      </div>
    </section>
  );
}

export function TimeLineChart({
  series,
  valueFormat,
  height = 260,
}: {
  series: LineSeries[];
  valueFormat: (v: number) => string;
  height?: number;
}) {
  const data = mergeByDate(series);
  const tooltip = ({ active, payload, label }: TooltipContentProps<ValueType, NameType>) => {
    if (!active || !payload?.length) return null;
    return (
      <TooltipBox title={fmtMonth(String(label), "long")}>
        {series.map((s) => {
          const item = payload.find((p) => p.dataKey === s.key);
          return (
            <p key={s.key} className="flex items-center justify-between gap-4">
              <span className="inline-flex items-center gap-1.5 text-muted">
                <Swatch color={s.color} />
                {s.label}
              </span>
              <span className="font-medium tabular-nums text-foreground">
                {item?.value === undefined ? "—" : valueFormat(Number(item.value))}
              </span>
            </p>
          );
        })}
      </TooltipBox>
    );
  };
  return (
    <div className="space-y-3">
      <Legend items={series.map((s) => ({ label: s.label, color: s.color }))} />
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis dataKey="date" tickFormatter={(d) => fmtMonth(d)} tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={28} />
            <YAxis tickFormatter={(v) => valueFormat(v)} tick={AXIS} tickLine={false} axisLine={false} width={56} domain={["auto", "auto"]} />
            <Tooltip content={tooltip} cursor={{ stroke: "var(--subtle)", strokeWidth: 1, strokeDasharray: "3 3" }} />
            {series.map((s) => (
              <Line
                key={s.key}
                dataKey={s.key}
                name={s.label}
                stroke={s.color}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 2, stroke: "#fff" }}
                connectNulls={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function TimeBarChart({
  points,
  label,
  valueFormat,
  color = SERIES_COLORS[0],
  height = 200,
}: {
  points: { date: string; value: number }[];
  label: string;
  valueFormat: (v: number) => string;
  color?: string;
  height?: number;
}) {
  const tooltip = ({ active, payload, label: d }: TooltipContentProps<ValueType, NameType>) =>
    active && payload?.length ? (
      <TooltipBox title={fmtMonth(String(d), "long")}>
        <p className="flex items-center justify-between gap-4">
          <span className="inline-flex items-center gap-1.5 text-muted">
            <Swatch color={color} shape="square" />
            {label}
          </span>
          <span className="font-medium tabular-nums">{valueFormat(Number(payload[0].value))}</span>
        </p>
      </TooltipBox>
    ) : null;
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barCategoryGap={2}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="date" tickFormatter={(d) => fmtMonth(d)} tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={28} />
          <YAxis tickFormatter={(v) => valueFormat(v)} tick={AXIS} tickLine={false} axisLine={false} width={56} />
          <Tooltip content={tooltip} cursor={{ fill: "rgba(11,27,51,0.04)" }} />
          <Bar dataKey="value" name={label} fill={color} radius={[4, 4, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Plain table used by the Table view of a chart. */
export function SeriesTable({ series, valueFormat }: { series: LineSeries[]; valueFormat: (v: number) => string }) {
  const rows = mergeByDate(series).reverse();
  return (
    <table className="w-full text-xs">
      <thead className="sticky top-0 bg-surface">
        <tr className="border-b border-border text-left text-muted">
          <th className="py-1.5 pr-3 font-medium">Month</th>
          {series.map((s) => (
            <th key={s.key} className="py-1.5 pr-3 text-right font-medium">{s.label}</th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y divide-border tabular-nums">
        {rows.map((r) => (
          <tr key={r.date}>
            <td className="py-1.5 pr-3">{fmtMonth(r.date, "long")}</td>
            {series.map((s) => (
              <td key={s.key} className="py-1.5 pr-3 text-right">
                {r[s.key] === undefined ? "—" : valueFormat(Number(r[s.key]))}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
