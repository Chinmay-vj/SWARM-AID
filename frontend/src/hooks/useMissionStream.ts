/**
 * One event-stream subscription per selected mission. Applies events to the activity store and
 * invalidates the affected query scopes (batched every 400 ms). Cleans up on mission change,
 * mode change and logout. Exposes reconnect() for the UI.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";
import type { MissionEvent } from "../contracts/api";
import { eventTopic } from "../contracts/events";
import type { Subscription } from "../services/providers/types";
import { useActivity } from "../stores/activity";
import { useConnection } from "../stores/connection";
import { useSession } from "../stores/session";
import { keys, useProvider } from "./data";

const TOPIC_SCOPES: Record<string, string[]> = {
  mission: ["detail", "summary", "history", "metrics", "map"],
  agents: ["agents", "agent", "map", "summary"],
  observations: ["observations", "summary"],
  incidents: ["incidents", "incident", "map", "summary", "review"],
  hazards: ["hazards", "environment", "map", "summary"],
  recommendations: ["recommendations", "recommendation", "review", "summary"],
  review: ["review", "decisions", "recommendations", "recommendation", "incidents", "incident"],
  alerts: ["alerts", "summary"],
  coverage: ["tasks", "coverage", "map"],
  communication: ["detail", "metrics"],
  model2: ["detail", "metrics"],
  metrics: ["metrics", "analytics"],
};

export function scopesForEvents(events: Pick<MissionEvent, "event_type">[]): Set<string> {
  const scopes = new Set<string>();
  for (const e of events)
    (TOPIC_SCOPES[eventTopic(e.event_type)] ?? ["detail"]).forEach((s) => scopes.add(s));
  return scopes;
}

export function useMissionStream(missionId: string | undefined, startSequence: number | undefined) {
  const provider = useProvider();
  const authenticated = useSession((s) => s.status === "authenticated");
  const client = useQueryClient();
  const subscription = useRef<Subscription | null>(null);
  const ready = startSequence !== undefined;

  useEffect(() => {
    useActivity.getState().switchMission(missionId ?? null);
  }, [missionId]);

  useEffect(() => {
    if (!missionId || !authenticated || !ready) return;
    const connection = useConnection.getState();
    connection.reset();
    let pending: MissionEvent[] = [];
    let timer: ReturnType<typeof setTimeout> | null = null;
    const flush = () => {
      timer = null;
      const batch = pending;
      pending = [];
      useActivity.getState().ingest(missionId, batch, provider.mode === "synthetic");
      for (const scope of scopesForEvents(batch))
        void client.invalidateQueries({ queryKey: keys.scoped(provider.mode, missionId, scope) });
    };
    // Start from a recent point so the timeline has context without replaying the full log.
    const after = Math.max(0, (startSequence ?? 0) - 150);
    const sub = provider.subscribe(missionId, after, {
      onEvent: (event) => {
        if (event.mission_id !== missionId) return; // never apply another mission's events
        useConnection.getState().markEvent();
        pending.push(event);
        if (!timer) timer = setTimeout(flush, 400);
      },
      onStatus: (status, detail) => useConnection.getState().setStream(status, detail ?? null),
      onResync: () => {
        useConnection.getState().markResync();
        void client.invalidateQueries({ queryKey: keys.scoped(provider.mode, missionId) });
      },
    });
    subscription.current = sub;
    return () => {
      if (timer) clearTimeout(timer);
      sub.close();
      subscription.current = null;
    };
    // startSequence is read once per mission/provider; later changes must not resubscribe.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [missionId, provider, authenticated, ready, client]);

  return useCallback(() => subscription.current?.reconnect(), []);
}
