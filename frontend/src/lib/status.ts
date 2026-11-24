/**
 * Mapping of backend status vocabularies to visual tones and labels. Every tone is always
 * paired with a text label and an icon glyph so status never relies on colour alone.
 */
export type Tone = "ok" | "warn" | "bad" | "info" | "muted" | "accent";

const TONES: Record<string, Tone> = {
  // mission
  draft: "muted",
  running: "ok",
  paused: "warn",
  completed: "info",
  stopped: "muted",
  failed: "bad",
  // agents / links
  available: "ok",
  connected: "ok",
  nominal: "ok",
  degraded: "warn",
  disconnected: "bad",
  unavailable: "bad",
  stale: "warn",
  unknown: "muted",
  inactive: "muted",
  ended: "muted",
  // incidents (Model 2 dispositions)
  reported: "info",
  human_review_pending: "warn",
  acknowledged: "ok",
  confirmed: "accent",
  rejected: "muted",
  corrected: "info",
  expired: "muted",
  resolution_reported: "info",
  closed: "muted",
  // recommendations
  pending: "warn",
  approved: "ok",
  revision_requested: "info",
  superseded: "muted",
  // decisions
  submitted: "info",
  accepted: "ok",
  recorded: "ok",
  // priority
  review_required: "info",
  elevated: "warn",
  potentially_urgent: "bad",
  // task knowledge
  coordinator_known: "ok",
  conflicting: "bad",
  // freshness
  fresh: "ok",
  missing: "muted",
  // health
  ok: "ok",
  ready: "ok",
  healthy: "ok",
  not_ready: "bad",
};

export function toneFor(status: string | null | undefined): Tone {
  if (!status) return "muted";
  return TONES[status] ?? "info";
}

export const TONE_GLYPH: Record<Tone, string> = {
  ok: "●",
  warn: "▲",
  bad: "■",
  info: "◆",
  muted: "○",
  accent: "★",
};

/** Human-readable label. Model 2 dispositions keep their backend meaning. */
const LABELS: Record<string, string> = {
  human_review_pending: "review pending",
  resolution_reported: "resolution reported",
  revision_requested: "revision requested",
  potentially_urgent: "potentially urgent",
  review_required: "review required",
  coordinator_known: "coordinator known",
  possible_human: "possible human",
  approve_review: "approve review",
  confirm_rescue_need: "confirm rescue need (simulated)",
  inspect_evidence: "inspect evidence",
  review_rescue_need: "review rescue need",
};

export function statusLabel(status: string | null | undefined): string {
  if (!status) return "unknown";
  return LABELS[status] ?? status.replace(/_/g, " ");
}

export const TERMINAL_MISSION_STATES = new Set(["completed", "stopped", "failed"]);
