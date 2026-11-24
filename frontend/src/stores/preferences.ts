/**
 * Non-sensitive UI preferences persisted in localStorage. No credentials, tokens or mission
 * records are ever stored here.
 */
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { TimeDisplay } from "../lib/format";

export type Theme = "system" | "dark" | "light";
export type Density = "comfortable" | "compact";

export const MAP_LAYERS = [
  "grid",
  "sectors",
  "coverage",
  "unknown",
  "hazards",
  "incidents",
  "sightings",
  "agents",
  "trails",
  "uncertainty",
  "labels",
] as const;
export type MapLayer = (typeof MAP_LAYERS)[number];

export interface Preferences {
  theme: Theme;
  density: Density;
  timeDisplay: TimeDisplay;
  reducedMotion: boolean;
  largeText: boolean;
  notifications: { enabled: boolean; minimum: "info" | "warning" | "critical"; toasts: boolean };
  mapLayers: Record<MapLayer, boolean>;
  mapSmoothing: boolean;
  playbackSpeed: number;
  autoScrollTimeline: boolean;
}

interface PreferenceActions {
  update(patch: Partial<Preferences>): void;
  toggleLayer(layer: MapLayer): void;
  reset(): void;
}

export const DEFAULT_PREFERENCES: Preferences = {
  theme: "system",
  density: "comfortable",
  timeDisplay: "local",
  reducedMotion: false,
  largeText: false,
  notifications: { enabled: true, minimum: "warning", toasts: true },
  mapLayers: {
    grid: true,
    sectors: true,
    coverage: true,
    unknown: true,
    hazards: true,
    incidents: true,
    sightings: true,
    agents: true,
    trails: true,
    uncertainty: true,
    labels: true,
  },
  mapSmoothing: true,
  playbackSpeed: 1,
  autoScrollTimeline: true,
};

const safeStorage = createJSONStorage(() => {
  try {
    const probe = "__swarm_aid_probe__";
    localStorage.setItem(probe, "1");
    localStorage.removeItem(probe);
    return localStorage;
  } catch {
    const memory = new Map<string, string>();
    return {
      getItem: (k) => memory.get(k) ?? null,
      setItem: (k, v) => void memory.set(k, v),
      removeItem: (k) => void memory.delete(k),
    };
  }
});

export const usePreferences = create<Preferences & PreferenceActions>()(
  persist(
    (set) => ({
      ...DEFAULT_PREFERENCES,
      update: (patch) => set(patch),
      toggleLayer: (layer) => set((s) => ({ mapLayers: { ...s.mapLayers, [layer]: !s.mapLayers[layer] } })),
      reset: () => set(DEFAULT_PREFERENCES),
    }),
    {
      name: "swarm-aid.preferences",
      version: 1,
      storage: safeStorage,
      partialize: ({ update: _u, toggleLayer: _t, reset: _r, ...prefs }) => prefs,
      merge: (persisted, current) => ({
        ...current,
        ...(persisted as Partial<Preferences>),
        mapLayers: { ...current.mapLayers, ...((persisted as Partial<Preferences>)?.mapLayers ?? {}) },
      }),
    },
  ),
);
