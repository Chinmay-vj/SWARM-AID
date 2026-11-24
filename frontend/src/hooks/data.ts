/**
 * TanStack Query bindings. Every key starts with [mode, scope, missionId?] so caches are
 * separated per data source and per mission; logout and mode changes clear the whole cache.
 */
import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useMemo } from "react";
import type { DataProvider } from "../services/providers/types";
import { getProvider } from "../services/providers";
import { useSession } from "../stores/session";
import { useConnection } from "../stores/connection";
import { asApiError } from "../services/api/errors";
import { permissionsFor, type Permission } from "../lib/permissions";

export function useProvider(): DataProvider {
  const mode = useSession((s) => s.mode);
  return useMemo(() => getProvider(mode), [mode]);
}

export function useMode() {
  return useSession((s) => s.mode);
}

export const keys = {
  missions: (mode: string) => [mode, "missions"] as const,
  mission: (mode: string, id: string) => [mode, "mission", id] as const,
  scoped: (mode: string, id: string, ...rest: unknown[]) => [mode, "mission", id, ...rest] as const,
  global: (mode: string, ...rest: unknown[]) => [mode, "global", ...rest] as const,
};

/** Live mission data refreshes slower when the event stream is healthy (events invalidate). */
export function useLiveInterval(active = true): number | false {
  const stream = useConnection((s) => s.stream);
  if (!active) return false;
  return stream === "open" ? 15_000 : 4_000;
}

interface Opts {
  enabled?: boolean;
  refetchInterval?: number | false;
  staleTime?: number;
}

export function useProviderQuery<T>(
  key: QueryKey,
  fn: (p: DataProvider, signal: AbortSignal) => Promise<T>,
  opts: Opts = {},
) {
  const provider = useProvider();
  return useQuery({
    queryKey: key,
    queryFn: async ({ signal }) => {
      const result = await fn(provider, signal);
      useConnection.getState().markSync();
      return result;
    },
    enabled: opts.enabled ?? true,
    refetchInterval: opts.refetchInterval,
    staleTime: opts.staleTime ?? 2_000,
    retry: (count, error) => asApiError(error).retryable && count < 2,
  });
}

/** Mission-scoped query: key [mode, "mission", missionId, ...parts]. */
export function useMissionQuery<T>(
  missionId: string | undefined,
  parts: unknown[],
  fn: (p: DataProvider, id: string, signal: AbortSignal) => Promise<T>,
  opts: Opts = {},
) {
  const mode = useMode();
  return useProviderQuery(
    keys.scoped(mode, missionId ?? "none", ...parts),
    (p, signal) => fn(p, missionId!, signal),
    { ...opts, enabled: Boolean(missionId) && (opts.enabled ?? true) },
  );
}

export function useMission(missionId: string | undefined) {
  const interval = useLiveInterval();
  return useMissionQuery(missionId, ["detail"], (p, id, s) => p.mission(id, s), {
    refetchInterval: interval,
  });
}

export function useMissionPermissions(missionId: string | undefined): Set<Permission> {
  const me = useSession((s) => s.me);
  return useMemo(() => permissionsFor(me, missionId), [me, missionId]);
}

/** Mutation that invalidates the mission scope on settle. Mutations are never retried. */
export function useMissionMutation<V, R>(
  missionId: string | undefined,
  fn: (p: DataProvider, vars: V) => Promise<R>,
) {
  const provider = useProvider();
  const mode = useMode();
  const client = useQueryClient();
  return useMutation({
    mutationFn: (vars: V) => fn(provider, vars),
    retry: false,
    onSettled: () => {
      if (missionId) void client.invalidateQueries({ queryKey: keys.scoped(mode, missionId) });
      void client.invalidateQueries({ queryKey: keys.missions(mode) });
    },
  });
}
