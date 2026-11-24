/**
 * Mission activity: bounded event timeline and local notifications for the selected mission.
 * Notifications are local to this browser (they are not backend alerts; backend alerts live
 * on the Human Review page and are acknowledged through the API).
 */
import { create } from "zustand";
import type { MissionEvent } from "../contracts/api";
import { NOTIFY_EVENTS, describeEvent, eventSeverity, type Severity } from "../contracts/events";

export const TIMELINE_CAPACITY = 400;
export const NOTIFICATION_CAPACITY = 100;

export interface LocalNotification {
  id: string;
  key: string;
  missionId: string;
  severity: Severity;
  title: string;
  eventType: string;
  sequence: number;
  simTimeMs: number | null;
  receivedAt: number;
  count: number;
  read: boolean;
  resourceType: string;
  resourceId: string;
  synthetic: boolean;
}

interface ActivityState {
  missionId: string | null;
  events: MissionEvent[];
  notifications: LocalNotification[];
  ingest(missionId: string, events: MissionEvent[], synthetic: boolean): void;
  local(
    n: Omit<LocalNotification, "id" | "count" | "read" | "receivedAt" | "sequence"> & { sequence?: number },
  ): void;
  markRead(id?: string): void;
  clear(): void;
  switchMission(missionId: string | null): void;
}

/** Notifications are deduplicated by resource + event type: repeats bump a counter. */
export function notificationKey(e: Pick<MissionEvent, "event_type" | "resource_id">): string {
  return `${e.event_type}:${e.resource_id}`;
}

export const useActivity = create<ActivityState>((set, get) => ({
  missionId: null,
  events: [],
  notifications: [],
  switchMission: (missionId) => {
    if (get().missionId !== missionId) set({ missionId, events: [], notifications: [] });
  },
  ingest: (missionId, incoming, synthetic) => {
    if (get().missionId !== missionId || incoming.length === 0) return;
    set((s) => {
      const known = new Set(s.events.map((e) => e.sequence));
      const fresh = incoming.filter((e) => !known.has(e.sequence));
      const events = [...fresh, ...s.events]
        .sort((a, b) => b.sequence - a.sequence)
        .slice(0, TIMELINE_CAPACITY);
      let notifications = s.notifications;
      for (const e of fresh) {
        if (!NOTIFY_EVENTS.has(e.event_type)) continue;
        const key = notificationKey(e);
        const existing = notifications.find((n) => n.key === key);
        if (existing) {
          notifications = notifications.map((n) =>
            n.key === key
              ? {
                  ...n,
                  count: n.count + 1,
                  read: false,
                  sequence: e.sequence,
                  simTimeMs: e.sim_time_ms,
                  title: describeEvent(e),
                }
              : n,
          );
        } else {
          notifications = [
            {
              id: `${missionId}:${e.sequence}`,
              key,
              missionId,
              severity: eventSeverity(e),
              title: describeEvent(e),
              eventType: e.event_type,
              sequence: e.sequence,
              simTimeMs: e.sim_time_ms,
              receivedAt: Date.now(),
              count: 1,
              read: false,
              resourceType: e.resource_type,
              resourceId: e.resource_id,
              synthetic,
            },
            ...notifications,
          ].slice(0, NOTIFICATION_CAPACITY);
        }
      }
      return { events, notifications };
    });
  },
  local: (n) =>
    set((s) => {
      const existing = s.notifications.find((x) => x.key === n.key);
      if (existing)
        return {
          notifications: s.notifications.map((x) =>
            x.key === n.key ? { ...x, count: x.count + 1, read: false } : x,
          ),
        };
      return {
        notifications: [
          {
            ...n,
            id: `local:${n.key}:${Date.now()}`,
            count: 1,
            read: false,
            receivedAt: Date.now(),
            sequence: n.sequence ?? 0,
          },
          ...s.notifications,
        ].slice(0, NOTIFICATION_CAPACITY),
      };
    }),
  markRead: (id) =>
    set((s) => ({
      notifications: s.notifications.map((n) => (!id || n.id === id ? { ...n, read: true } : n)),
    })),
  clear: () => set({ events: [], notifications: [] }),
}));
