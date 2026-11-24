/**
 * Idempotency keys for consequential human decisions. One key is created when a decision
 * dialog opens and reused for every retry of that same submission, so the backend returns
 * the original decision instead of recording a duplicate. Format matches the backend
 * constraint ^[A-Za-z0-9._:-]{8,100}$.
 */
export function newIdempotencyKey(prefix = "ui"): string {
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}:${random}`.slice(0, 100);
}

export const IDEMPOTENCY_PATTERN = /^[A-Za-z0-9._:-]{8,100}$/;
