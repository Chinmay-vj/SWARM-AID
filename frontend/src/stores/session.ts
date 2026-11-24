/**
 * Session store: active data mode and the authenticated identity. Tokens live in
 * services/api/tokens.ts (memory + tab session storage), never in this store or localStorage.
 * Only the chosen mode is remembered (sessionStorage) so a reload returns to the same source.
 */
import { create } from "zustand";
import type { Me } from "../contracts/api";
import type { DataMode } from "../services/providers/types";

const MODE_KEY = "swarm-aid.mode";

function initialMode(): DataMode {
  try {
    const saved = sessionStorage.getItem(MODE_KEY);
    if (saved === "connected" || saved === "synthetic") return saved;
  } catch {
    /* storage unavailable */
  }
  return import.meta.env.VITE_API_MODE === "synthetic" ? "synthetic" : "connected";
}

interface SessionState {
  mode: DataMode;
  me: Me | null;
  status: "anonymous" | "restoring" | "authenticated";
  expiredNotice: string | null;
  setMode(mode: DataMode): void;
  signedIn(me: Me): void;
  signedOut(notice?: string | null): void;
  setRestoring(): void;
}

export const useSession = create<SessionState>((set) => ({
  mode: initialMode(),
  me: null,
  status: "anonymous",
  expiredNotice: null,
  setMode: (mode) => {
    try {
      sessionStorage.setItem(MODE_KEY, mode);
    } catch {
      /* ignore */
    }
    set({ mode });
  },
  signedIn: (me) => set({ me, status: "authenticated", expiredNotice: null }),
  signedOut: (notice = null) => set({ me: null, status: "anonymous", expiredNotice: notice }),
  setRestoring: () => set({ status: "restoring" }),
}));
