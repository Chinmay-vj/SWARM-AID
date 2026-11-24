/**
 * Line and bar charts (Recharts) with an accessible text summary and a data table fallback.
 * Animations are disabled to keep live updates controlled and to respect reduced motion.
 */
import { useId } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ErrorBar,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { EmptyState } from "../ui/states";

export interface SeriesSpec {
  key: string;
  label: string;
  color: string;
}

export function summarizeSeries(
  points: Record<string, number | null>[],
  spec: SeriesSpec,
  x: string,
): string {
  const values = points.map((p) => p[spec.key]).filter((v): v is number => typeof v === "number");
  if (!values.length) return `${spec.label}: no measurements.`;
  const last = values[values.length - 1]!;
  return `${spec.label}: ${values.length} points from ${x} ${points[0]?.[x] ?? "?"} to ${points[points.length - 1]?.[x] ?? "?"}; latest ${round(last)}, min ${round(Math.min(...values))}, max ${round(Math.max(...values))}.`;
}

const round = (v: number) =>
  Math.abs(v) < 10 ? v.toFixed(3).replace(/\.?0+$/, "") : Math.round(v).toLocaleString();

export function SeriesChart({
  title,
  points,
  x,
  xLabel,
  series,
  yLabel,
  height = 220,
}: {
  title: string;
  points: Record<string, number | null>[];
  x: string;
  xLabel: string;
  series: SeriesSpec[];
  yLabel?: string;
  height?: number;
}) {
  const id = useId();
  if (points.length === 0) return <EmptyState title={`${title}: no measurements yet`} />;
  return (
    <figure style={{ margin: 0 }} aria-labelledby={`${id}-cap`}>
      <div className="chart-box" style={{ height }} aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 6, right: 12, bottom: 18, left: 0 }}>
            <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 3" />
            <XAxis
              dataKey={x}
              stroke="var(--muted)"
              fontSize={11}
              label={{
                value: xLabel,
                position: "insideBottom",
                offset: -8,
                fill: "var(--muted)",
                fontSize: 11,
              }}
            />
            <YAxis
              stroke="var(--muted)"
              fontSize={11}
              width={48}
              label={
                yLabel
                  ? { value: yLabel, angle: -90, position: "insideLeft", fill: "var(--muted)", fontSize: 11 }
                  : undefined
              }
            />
            <Tooltip
              contentStyle={{
                background: "var(--surface-2)",
                border: "1px solid var(--line)",
                color: "var(--text)",
              }}
            />
            {series.map((s) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stroke={s.color}
                dot={false}
                strokeWidth={2}
                isAnimationActive={false}
                connectNulls={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <figcaption id={`${id}-cap`} className="xs muted">
        {title}. {series.map((s) => summarizeSeries(points, s, xLabel)).join(" ")}
      </figcaption>
    </figure>
  );
}

export function MeanBarChart({
  title,
  rows,
  label,
  height = 240,
}: {
  title: string;
  rows: { name: string; mean: number | null; low: number | null; high: number | null }[];
  label: string;
  height?: number;
}) {
  const id = useId();
  const data = rows
    .filter((r) => r.mean !== null)
    .map((r) => ({
      name: r.name,
      mean: r.mean,
      err: r.low !== null && r.high !== null && r.mean !== null ? [r.mean - r.low, r.high - r.mean] : [0, 0],
    }));
  if (!data.length) return <EmptyState title="No measured values" />;
  return (
    <figure style={{ margin: 0 }} aria-labelledby={`${id}-cap`}>
      <div className="chart-box" style={{ height }} aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 6, right: 12, bottom: 40, left: 0 }}>
            <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 3" />
            <XAxis
              dataKey="name"
              stroke="var(--muted)"
              fontSize={10}
              angle={-20}
              textAnchor="end"
              interval={0}
            />
            <YAxis stroke="var(--muted)" fontSize={11} width={52} />
            <Tooltip
              contentStyle={{
                background: "var(--surface-2)",
                border: "1px solid var(--line)",
                color: "var(--text)",
              }}
            />
            <Bar dataKey="mean" name={`mean ${label}`} fill="var(--chart-1)" isAnimationActive={false}>
              <ErrorBar dataKey="err" width={6} stroke="var(--text)" />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <figcaption id={`${id}-cap`} className="xs muted">
        {title}. Bars show the mean {label} per group; whiskers show the 95% confidence interval where n ≥ 2.
        Exact values are in the table.
      </figcaption>
    </figure>
  );
}
