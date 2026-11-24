/**
 * Post-sign-in redirect target. Only same-application absolute paths are accepted; protocol-
 * relative ("//host"), backslash ("/\\host"), scheme ("https:") and control-character forms are
 * rejected. Mitigates the React Router v6 open-redirect advisories (GHSA-9jcx-v3wj-wh4m,
 * GHSA-wrjc-x8rr-h8h6) for the one navigation target that comes from the URL.
 */
export function safeRedirect(target: unknown, fallback = "/missions"): string {
  if (typeof target !== "string" || target.length === 0 || target.length > 2048) return fallback;
  if (!target.startsWith("/")) return fallback;
  if (target.startsWith("//") || target.startsWith("/\\")) return fallback;
  if (target.includes("\\")) return fallback;
  for (let i = 0; i < target.length; i++) {
    const code = target.charCodeAt(i);
    if (code < 0x20 || code === 0x7f) return fallback;
  }
  if (/^\/[a-z][a-z0-9+.-]*:/i.test(target)) return fallback;
  return target;
}
