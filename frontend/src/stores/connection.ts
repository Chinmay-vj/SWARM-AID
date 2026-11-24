/**
 * Connection and stream state (not persisted). Records browser-observed API latency and
 * errors so System Health can show client-side measurements next to backend health.
 */
import { create } from "zustand";
import type { StreamStatus } from "../services/providers/types";

export interface ApiSample {
  method: string;
  path: string;
  status: number | null;
  ms: number;
  at: number;
}

interface ConnectionState {
  backend: "unknown" | "online" | "not_ready" | "offline";
  lastProbeAt: number | null;
  stream: StreamStatus;
  streamDetail: string | null;
  lastEventAt: number | null;
  lastSyncAt: number | null;
  resyncCount: number;
  samples: ApiSample[];
  setBackend(state: ConnectionState["backend"]): void;
  setStream(status: StreamStatus, detail?: string | null): void;
  markEvent(): void;
  markSync(): void;
  markResync(): void;
  reset(): void;
}

export const useConnection = create<ConnectionState>((set) => ({
  backend: "unknown",
  lastProbeAt: null,
  stream: "idle",
  streamDetail: null,
  lastEventAt: null,
  lastSyncAt: null,
  resyncCount: 0,
  samples: [],
  setBackend: (backend) => set({ backend, lastProbeAt: Date.now() }),
  setStream: (stream, detail = null) => set({ stream, streamDetail: detail }),
  markEvent: () => set({ lastEventAt: Date.now(), lastSyncAt: Date.now() }),
  markSync: () => set({ lastSyncAt: Date.now() }),
  markResync: () => set((s) => ({ resyncCount: s.resyncCount + 1 })),
  reset: () =>
    set({ stream: "idle", streamDetail: null, lastEventAt: null, lastSyncAt: null, resyncCount: 0 }),
}));

/** Bounded (last 300) request samples, recorded outside React render. */
export function recordApiSample(sample: Omit<ApiSample, "at">): void {
  useConnection.setState((s) => ({
    samples: [...s.samples.slice(-299), { ...sample, path: normalizePath(sample.path), at: Date.now() }],
  }));
}

/** Replace identifiers so samples group by route, not by resource. */
export function normalizePath(path: string): string {
  return path
    .replace(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi, "{id}")
    .replace(/[0-9a-f]{32}/gi, "{id}");
}
