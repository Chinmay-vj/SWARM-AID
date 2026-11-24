/**
 * Currently selected mission, published by MissionLayout for the shell (top bar, sidebar,
 * banner) which render outside the mission route. Cleared when leaving the mission.
 */
import { create } from "zustand";
import type { Mission } from "../../contracts/api";

export interface MissionContextValue {
  mission: Mission;
  pendingReviews: number;
  reconnect: () => void;
}

interface Store {
  value: MissionContextValue | null;
  set(value: MissionContextValue | null): void;
}

export const useMissionStore = create<Store>((set) => ({ value: null, set: (value) => set({ value }) }));

export function useMissionContext(): MissionContextValue | null {
  return useMissionStore((s) => s.value);
}
