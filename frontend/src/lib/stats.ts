/**
 * Descriptive statistics for stored experiment results. These summarize measured values only;
 * missing values are excluded and counted, never imputed.
 */
export interface Summary {
  n: number;
  missing: number;
  mean: number | null;
  median: number | null;
  sd: number | null;
  min: number | null;
  max: number | null;
  /** 95% confidence interval for the mean (Student t). Null when n < 2. */
  ci95: [number, number] | null;
}

// Two-sided 95% Student t critical values for df = 1..30; df > 30 uses the normal value.
const T95 = [
  12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.16, 2.145, 2.131,
  2.12, 2.11, 2.101, 2.093, 2.086, 2.08, 2.074, 2.069, 2.064, 2.06, 2.056, 2.052, 2.048, 2.045, 2.042,
];

export function tCritical95(df: number): number {
  if (df < 1) return Number.NaN;
  return df <= 30 ? T95[df - 1]! : 1.96;
}

export function summarize(values: readonly (number | null | undefined)[]): Summary {
  const xs = values.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  const missing = values.length - xs.length;
  const n = xs.length;
  if (n === 0) return { n, missing, mean: null, median: null, sd: null, min: null, max: null, ci95: null };
  const sorted = [...xs].sort((a, b) => a - b);
  const mean = xs.reduce((a, b) => a + b, 0) / n;
  const mid = Math.floor(n / 2);
  const median = n % 2 ? sorted[mid]! : (sorted[mid - 1]! + sorted[mid]!) / 2;
  const sd = n > 1 ? Math.sqrt(xs.reduce((a, b) => a + (b - mean) ** 2, 0) / (n - 1)) : null;
  const ci95: [number, number] | null =
    sd !== null
      ? [mean - (tCritical95(n - 1) * sd) / Math.sqrt(n), mean + (tCritical95(n - 1) * sd) / Math.sqrt(n)]
      : null;
  return { n, missing, mean, median, sd, min: sorted[0]!, max: sorted[n - 1]!, ci95 };
}

export type Row = Record<string, string | number>;

/** Group rows by the given keys and summarize a numeric metric per group. */
export function groupSummaries(
  rows: readonly Row[],
  keys: readonly string[],
  metric: string,
): { group: Row; summary: Summary }[] {
  const groups = new Map<string, { group: Row; values: (number | null)[] }>();
  for (const row of rows) {
    const group: Row = {};
    for (const k of keys) group[k] = row[k] ?? "";
    const id = JSON.stringify(keys.map((k) => group[k]));
    const bucket = groups.get(id) ?? { group, values: [] };
    const value = row[metric];
    bucket.values.push(typeof value === "number" ? value : null);
    groups.set(id, bucket);
  }
  return [...groups.values()].map(({ group, values }) => ({ group, summary: summarize(values) }));
}

export function numericColumns(rows: readonly Row[], columns: readonly string[]): string[] {
  return columns.filter((c) => rows.length > 0 && rows.every((r) => typeof r[c] === "number"));
}
