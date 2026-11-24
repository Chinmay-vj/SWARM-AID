import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { getProvider } from "../services/providers";
import type { DataMode } from "../services/providers/types";
import { useActivity } from "../stores/activity";
import { useConnection } from "../stores/connection";
import { useSession } from "../stores/session";

/**
 * Logout and mode switching. Both clear every cached query, the event timeline and local
 * notifications so nothing from one session or data source leaks into another.
 */
export function useAuthActions() {
  const client = useQueryClient();
  const navigate = useNavigate();
  const { mode, setMode, signedOut } = useSession();

  const clearAll = useCallback(() => {
    client.cancelQueries();
    client.clear();
    useActivity.getState().clear();
    useActivity.getState().switchMission(null);
    useConnection.getState().reset();
  }, [client]);

  const logout = useCallback(
    async (notice?: string) => {
      try {
        await getProvider(mode).logout();
      } catch {
        /* the local session is cleared regardless */
      }
      clearAll();
      signedOut(notice ?? null);
      navigate("/login", { replace: true });
    },
    [mode, clearAll, signedOut, navigate],
  );

  const switchMode = useCallback(
    async (next: DataMode) => {
      try {
        await getProvider(mode).logout();
      } catch {
        /* ignore */
      }
      clearAll();
      signedOut(null);
      setMode(next);
      navigate("/login", { replace: true });
    },
    [mode, clearAll, signedOut, setMode, navigate],
  );

  return { logout, switchMode };
}
