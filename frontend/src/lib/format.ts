/** Formatting helpers. Simulation time and wall-clock time are always kept distinct. */
import type { Location } from "../contracts/api";

/** Simulation time (milliseconds since mission start) as "T+mm:ss.s". */
export function formatSimTime(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return "T+—";
  const negative = ms < 0;
  const total = Math.abs(ms) / 1000;
  const minutes = Math.floor(total / 60);
  const seconds = (total % 60).toFixed(1).padStart(4, "0");
  return `T${negative ? "−" : "+"}${String(minutes).padStart(2, "0")}:${seconds}`;
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return "—";
  if (Math.abs(ms) < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (Math.abs(s) < 60) return `${s.toFixed(1)} s`;
  return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
}

export type TimeDisplay = "local" | "utc";

/** Wall-clock timestamp. Invalid input renders as "unknown" rather than a wrong date. */
export function formatWallTime(iso: string | null | undefined, mode: TimeDisplay = "local"): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "unknown";
  if (mode === "utc") return `${date.toISOString().replace("T", " ").slice(0, 19)} UTC`;
  return date.toLocaleString(undefined, { hour12: false });
}

/** Confidence in [0,1] as a percentage. Unknown confidence stays unknown (never 0%). */
export function formatConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "unknown";
  return `${Math.round(value * 100)}%`;
}

export function formatFraction(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "unknown";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatNumber(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

/**
 * Reported location with its coordinate system. Missing coordinates are "not reported",
 * never (0,0). Local grid cells are labelled as such so they are not mistaken for GPS.
 */
export function formatLocation(loc: Location | null | undefined): string {
  if (!loc) return "not reported";
  const unc =
    loc.uncertainty === null || loc.uncertainty === undefined
      ? "uncertainty unknown"
      : `±${loc.uncertainty} ${loc.units}`;
  if (loc.crs === "swarm-aid:grid") return `cell (${trim(loc.x)}, ${trim(loc.y)}) · ${unc}`;
  return `${loc.crs} (${trim(loc.x)}, ${trim(loc.y)}) · ${unc}`;
}

function trim(v: number): string {
  return Number.isInteger(v) ? String(v) : v.toFixed(2);
}

export function shortId(id: string | null | undefined): string {
  if (!id) return "—";
  return id.length > 12 ? id.slice(0, 8) : id;
}

export function humanize(value: string | null | undefined): string {
  if (!value) return "unknown";
  return value.replace(/_/g, " ");
}
