"use client";

import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
  type TooltipValueType as ValueType,
} from "recharts";
import type { NameType } from "recharts/types/component/DefaultTooltipContent";
import { SERIES_COLORS } from "@/components/charts";
import { fmtMonth } from "@/lib/format";

const AXIS = { fontSize: 11, fill: "var(--muted)" };
const GRID = "#eceef2";

function Swatch({ color, shape = "line" }: { color: string; shape?: "line" | "square" }) {
  return shape === "line" ? (
    <span aria-hidden className="inline-block h-0.5 w-3 rounded-full" style={{ background: color }} />
  ) : (
    <span aria-hidden className="inline-block size-2.5 rounded-sm" style={{ background: color }} />
  );
}

function Box({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="min-w-44 rounded-md border border-border bg-surface px-3 py-2 text-xs shadow-[0_4px_12px_rgba(11,27,51,0.08)]">
      <p className="mb-1.5 font-medium text-foreground">{title}</p>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

export type ForecastChartPoint = { date: string; value: number; lower: number; upper: number };

type FRow = { date: string; actual?: number; forecast?: number; band?: [number, number]; lower?: number; upper?: number };

/**
 * Observed history (solid) joined to the forecast (dashed) with its prediction interval
 * as a translucent band. One series, one axis; the band is named in the legend.
 */
export function ForecastChart({
  history,
  forecast,
  valueFormat,
  height = 260,
  historyLabel = "Observed",
}: {
  history: { date: string; value: number }[];
  forecast: ForecastChartPoint[];
  valueFormat: (v: number) => string;
  height?: number;
  historyLabel?: string;
}) {
  const color = SERIES_COLORS[0];
  const rows: FRow[] = history.map((p) => ({ date: p.date, actual: p.value }));
  const last = history[history.length - 1];
  if (last && forecast.length) {
    rows[rows.length - 1] = { ...rows[rows.length - 1], forecast: last.value, band: [last.value, last.value] };
  }
  for (const f of forecast) rows.push({ date: f.date, forecast: f.value, band: [f.lower, f.upper], lower: f.lower, upper: f.upper });

  const tooltip = ({ active, payload, label }: TooltipContentProps<ValueType, NameType>) => {
    if (!active || !payload?.length) return null;
    const row = payload[0].payload as FRow;
    return (
      <Box title={fmtMonth(String(label), "long")}>
        {row.actual !== undefined ? (
          <p className="flex items-center justify-between gap-4">
            <span className="inline-flex items-center gap-1.5 text-muted"><Swatch color={color} />{historyLabel}</span>
            <span className="font-medium tabular-nums">{valueFormat(row.actual)}</span>
          </p>
        ) : (
          <>
            <p className="flex items-center justify-between gap-4">
              <span className="inline-flex items-center gap-1.5 text-muted"><Swatch color={color} />Forecast</span>
              <span className="font-medium tabular-nums">{valueFormat(row.forecast!)}</span>
            </p>
            <p className="flex items-center justify-between gap-4 text-muted">
              <span>Range</span>
              <span className="tabular-nums">{valueFormat(row.lower!)} – {valueFormat(row.upper!)}</span>
            </p>
          </>
        )}
      </Box>
    );
  };

  return (
    <div className="space-y-3">
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted" aria-label="Legend">
        <li className="inline-flex items-center gap-1.5"><Swatch color={color} />{historyLabel}</li>
        <li className="inline-flex items-center gap-1.5">
          <span aria-hidden className="inline-block w-3 border-t-2 border-dashed" style={{ borderColor: color }} />Forecast
        </li>
        <li className="inline-flex items-center gap-1.5">
          <span aria-hidden className="inline-block size-2.5 rounded-sm" style={{ background: color, opacity: 0.2 }} />Prediction interval
        </li>
      </ul>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis dataKey="date" tickFormatter={(d) => fmtMonth(d)} tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={28} />
            <YAxis tickFormatter={(v) => valueFormat(v)} tick={AXIS} tickLine={false} axisLine={false} width={56} domain={["auto", "auto"]} />
            <Tooltip content={tooltip} cursor={{ stroke: "var(--subtle)", strokeWidth: 1, strokeDasharray: "3 3" }} />
            <Area dataKey="band" stroke="none" fill={color} fillOpacity={0.2} isAnimationActive={false} activeDot={false} />
            <Line dataKey="actual" stroke={color} strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: "#fff" }} isAnimationActive={false} />
            <Line dataKey="forecast" stroke={color} strokeWidth={2} strokeDasharray="5 4" dot={{ r: 3, fill: color, strokeWidth: 0 }} activeDot={{ r: 4, strokeWidth: 2, stroke: "#fff" }} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/** Diverging pair from the validated palette: blue = saving, red = extra cost. */
export const IMPACT_COLORS = { saving: "#2a78d6", cost: "#e34948" } as const;

export function ImpactBars({
  items,
  valueFormat,
}: {
  items: { label: string; value: number; note?: string }[];
  valueFormat: (v: number) => string;
}) {
  const height = Math.max(120, items.length * 40 + 24);
  const tooltip = ({ active, payload }: TooltipContentProps<ValueType, NameType>) => {
    if (!active || !payload?.length) return null;
    const row = payload[0].payload as { label: string; value: number; note?: string };
    return (
      <Box title={row.label}>
        <p className="flex items-center justify-between gap-4">
          <span className="inline-flex items-center gap-1.5 text-muted">
            <Swatch color={row.value > 0 ? IMPACT_COLORS.cost : IMPACT_COLORS.saving} shape="square" />
            {row.value > 0 ? "Extra cost" : row.value < 0 ? "Saving" : "No change"}
          </span>
          <span className="font-medium tabular-nums">{valueFormat(row.value)}</span>
        </p>
        {row.note && <p className="max-w-64 text-[11px] leading-snug text-muted">{row.note}</p>}
      </Box>
    );
  };
  return (
    <div className="space-y-3">
      <ul className="flex flex-wrap gap-x-4 text-xs text-muted" aria-label="Legend">
        <li className="inline-flex items-center gap-1.5"><Swatch color={IMPACT_COLORS.cost} shape="square" />Extra cost</li>
        <li className="inline-flex items-center gap-1.5"><Swatch color={IMPACT_COLORS.saving} shape="square" />Saving</li>
      </ul>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={items} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }} barCategoryGap={8}>
            <CartesianGrid stroke={GRID} horizontal={false} />
            <XAxis type="number" tickFormatter={(v) => valueFormat(v)} tick={AXIS} tickLine={false} axisLine={false} />
            <YAxis type="category" dataKey="label" tick={AXIS} tickLine={false} axisLine={false} width={160} />
            <ReferenceLine x={0} stroke="var(--subtle)" />
            <Tooltip content={tooltip} cursor={{ fill: "rgba(11,27,51,0.04)" }} />
            <Bar dataKey="value" radius={4} isAnimationActive={false}>
              {items.map((it) => (
                <Cell key={it.label} fill={it.value > 0 ? IMPACT_COLORS.cost : IMPACT_COLORS.saving} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
