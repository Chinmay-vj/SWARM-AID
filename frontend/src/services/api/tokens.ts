/**
 * Session token storage for the connected mode.
 *
 * The Phase 7 backend issues bearer access/refresh tokens in JSON (no HttpOnly cookies).
 *  - The access token (15 min) is kept in memory only.
 *  - The refresh token is kept in sessionStorage (tab-scoped, cleared when the tab closes and on
 *    logout) so a page refresh can recover the session. This exposes it to scripts running in
 *    the page; the build forbids HTML injection and the preview server sends a strict CSP.
 *    See docs/frontend/AUTHENTICATION.md for the trade-off.
 *  - Passwords are never stored.
 */
import type { TokenResponse } from "../../contracts/api";

const REFRESH_KEY = "swarm-aid.refresh";

type Listener = (state: "updated" | "expired" | "cleared") => void;

class SessionTokens {
  private accessToken: string | null = null;
  private accessExpiresAt: number | null = null;
  private refreshExpiresAt: number | null = null;
  private listeners = new Set<Listener>();

  access(): string | null {
    return this.accessToken;
  }

  refresh(): string | null {
    try {
      return sessionStorage.getItem(REFRESH_KEY);
    } catch {
      return null;
    }
  }

  get accessExpiry(): number | null {
    return this.accessExpiresAt;
  }

  get refreshExpiry(): number | null {
    return this.refreshExpiresAt;
  }

  update(tokens: TokenResponse): void {
    this.accessToken = tokens.access_token;
    this.accessExpiresAt = Date.parse(tokens.access_expires_at);
    this.refreshExpiresAt = Date.parse(tokens.refresh_expires_at);
    try {
      sessionStorage.setItem(REFRESH_KEY, tokens.refresh_token);
    } catch {
      /* storage unavailable: session will not survive a reload */
    }
    this.emit("updated");
  }

  expired(): void {
    this.clearValues();
    this.emit("expired");
  }

  clear(): void {
    this.clearValues();
    this.emit("cleared");
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private clearValues(): void {
    this.accessToken = null;
    this.accessExpiresAt = null;
    this.refreshExpiresAt = null;
    try {
      sessionStorage.removeItem(REFRESH_KEY);
    } catch {
      /* ignore */
    }
  }

  private emit(state: "updated" | "expired" | "cleared"): void {
    this.listeners.forEach((l) => l(state));
  }
}

export const sessionTokens = new SessionTokens();
export type { SessionTokens };
