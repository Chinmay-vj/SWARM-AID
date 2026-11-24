/**
 * Mission scope: loads the mission (404/403 → explicit state), opens the single event stream
 * for it, publishes it to the shell, and tears everything down on mission change.
 */
import { useEffect } from "react";
import { Link, Outlet, useParams } from "react-router-dom";
import { keys, useMission, useMissionQuery, useMode, useProviderQuery } from "../../hooks/data";
import { useSession } from "../../stores/session";
import { useMissionStream } from "../../hooks/useMissionStream";
import { asApiError } from "../../services/api/errors";
import { ErrorState, Skeleton } from "../../components/ui/states";
import { useMissionStore } from "./missionContext";

export function MissionLayout() {
  const { missionId } = useParams();
  const mission = useMission(missionId);
  const review = useMissionQuery(missionId, ["review"], (p, id, s) => p.reviewQueue(id, s), {
    enabled: Boolean(mission.data),
    refetchInterval: 10_000,
  });
  const reconnect = useMissionStream(mission.data ? missionId : undefined, mission.data?.last_event_sequence);
  const set = useMissionStore((s) => s.set);
  // Memberships change server-side (mission creation, a coordinator adding members). Refresh
  // the identity when entering a mission so permission-aware controls match the backend.
  const mode = useMode();
  const me = useProviderQuery(keys.global(mode, "me", missionId), (p) => p.me(), { staleTime: 30_000 });
  useEffect(() => {
    const current = useSession.getState().me;
    if (me.data && JSON.stringify(me.data) !== JSON.stringify(current))
      useSession.getState().signedIn(me.data);
  }, [me.data]);

  useEffect(() => {
    if (mission.data) set({ mission: mission.data, pendingReviews: review.data?.length ?? 0, reconnect });
  }, [mission.data, review.data, reconnect, set]);
  useEffect(() => () => set(null), [missionId, set]);

  if (mission.isLoading) return <Skeleton rows={6} />;
  if (!mission.data) {
    const e = asApiError(mission.error);
    return (
      <div className="panel">
        <ErrorState
          error={mission.error}
          title={
            e.kind === "not_found"
              ? "Mission not found"
              : e.kind === "forbidden"
                ? "Mission not available to you"
                : undefined
          }
          onRetry={() => void mission.refetch()}
        />
        <p className="small" style={{ textAlign: "center" }}>
          <Link to="/missions">Back to missions</Link>
        </p>
      </div>
    );
  }
  return <Outlet />;
}
