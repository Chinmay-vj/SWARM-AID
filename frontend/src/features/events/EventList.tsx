import { Pause, Play } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { MissionEvent } from "../../contracts/api";
import { describeEvent, eventResourcePath, eventSeverity, eventTopic } from "../../contracts/events";
import { Button, StatusBadge } from "../../components/ui/primitives";
import { EmptyState } from "../../components/ui/states";
import { formatSimTime } from "../../lib/format";
import { usePreferences } from "../../stores/preferences";

const TONE = { critical: "bad", warning: "warn", success: "ok", info: "info" } as const;

export function EventList({
  events,
  missionId,
  maxHeight = 360,
  limit = 80,
  synthetic,
}: {
  events: MissionEvent[];
  missionId: string;
  maxHeight?: number;
  limit?: number;
  synthetic?: boolean;
}) {
  const autoScroll = usePreferences((s) => s.autoScrollTimeline);
  const timeDisplay = usePreferences((s) => s.timeDisplay);
  const [paused, setPaused] = useState(!autoScroll);
  const [frozen, setFrozen] = useState<MissionEvent[] | null>(null);
  const newest = useRef(0);
  const shown = (paused ? (frozen ?? events) : events).slice(0, limit);
  const fresh = useMemo(
    () => new Set(shown.filter((e) => e.sequence > newest.current).map((e) => e.sequence)),
    [shown],
  );
  useEffect(() => {
    if (shown[0]) newest.current = Math.max(newest.current, shown[0].sequence);
  }, [shown]);
  const pendingCount =
    paused && frozen ? events.filter((e) => e.sequence > (frozen[0]?.sequence ?? 0)).length : 0;

  return (
    <div className="stack tight">
      <div className="row between">
        <span className="xs muted">
          {synthetic ? "Synthetic playback events" : "Backend domain events"} · newest first · simulation time
          (T+) and wall clock
        </span>
        <Button
          size="sm"
          icon={paused ? <Play size={12} aria-hidden="true" /> : <Pause size={12} aria-hidden="true" />}
          aria-pressed={paused}
          onClick={() => {
            setFrozen(paused ? null : events);
            setPaused(!paused);
          }}
        >
          {paused ? `Resume live${pendingCount ? ` (${pendingCount} new)` : ""}` : "Pause updates"}
        </Button>
      </div>
      {shown.length === 0 ? (
        <EmptyState title="No events yet">Events appear when the mission is running.</EmptyState>
      ) : (
        <ul
          className="timeline"
          style={{ maxHeight }}
          aria-label="Event timeline"
          aria-live={paused ? "off" : "polite"}
          aria-relevant="additions"
        >
          {shown.map((e) => {
            const path = eventResourcePath(missionId, e);
            const sev = eventSeverity(e);
            return (
              <li key={e.sequence} className={fresh.has(e.sequence) ? "new" : ""}>
                <span className="t">
                  {formatSimTime(e.sim_time_ms)}
                  <br />
                  {timeDisplay === "utc"
                    ? e.occurred_at.slice(11, 19)
                    : new Date(e.occurred_at).toLocaleTimeString()}
                </span>
                <div>
                  <div className="row" style={{ gap: 6 }}>
                    <StatusBadge status={sev} tone={TONE[sev]} label={eventTopic(e.event_type)} />
                    <span className="meta">
                      #{e.sequence} · {e.source}
                    </span>
                  </div>
                  <div>{path ? <Link to={path}>{describeEvent(e)}</Link> : describeEvent(e)}</div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
