/**
 * Supported mission lifecycle controls (start, pause, resume, stop) with explicit confirmation,
 * plus synthetic playback controls in demo mode. Only valid transitions are offered; the
 * backend validates again and its refusal is shown.
 */
import { Pause, Play, RotateCcw, SkipForward, Square } from "lucide-react";
import { useState } from "react";
import type { LifecycleAction, Mission } from "../../contracts/api";
import { ConfirmDialog } from "../../components/ui/dialogs";
import { Button } from "../../components/ui/primitives";
import { TextField } from "../../components/ui/data";
import { AlertBox } from "../../components/ui/states";
import { useMissionMutation, useMissionPermissions, useProvider } from "../../hooks/data";
import { deniedReason } from "../../lib/permissions";
import { syntheticControls } from "../../services/providers";
import { asApiError } from "../../services/api/errors";
import { usePreferences } from "../../stores/preferences";
import { useQueryClient } from "@tanstack/react-query";

const AVAILABLE: Record<string, LifecycleAction[]> = {
  draft: ["start"],
  running: ["pause", "stop"],
  paused: ["resume", "stop"],
};
const CONSEQUENCE: Record<LifecycleAction, string> = {
  start:
    "Starts the simulation run for this mission. Model 1 agents begin reporting and Model 2 begins assessing.",
  pause:
    "Pauses the simulation clock. Pending recommendations do not expire while paused, which gives reviewers time to decide.",
  resume: "Resumes the simulation clock from where it paused.",
  stop: "Ends this simulation run. It cannot be resumed. Persisted records remain available.",
};

export function MissionControls({ mission }: { mission: Mission }) {
  const perms = useMissionPermissions(mission.id);
  const provider = useProvider();
  const [action, setAction] = useState<LifecycleAction | null>(null);
  const [reason, setReason] = useState("");
  const mutation = useMissionMutation(mission.id, (p, v: { action: LifecycleAction; reason: string }) =>
    p.controlMission(mission.id, v.action, v.reason),
  );
  const allowed = perms.has("mission.control");
  const actions = AVAILABLE[mission.status] ?? [];
  const icon = {
    start: <Play size={14} aria-hidden="true" />,
    pause: <Pause size={14} aria-hidden="true" />,
    resume: <Play size={14} aria-hidden="true" />,
    stop: <Square size={14} aria-hidden="true" />,
  };

  return (
    <div className="row">
      {actions.map((a) => (
        <Button
          key={a}
          variant={a === "stop" ? "bad" : a === "start" || a === "resume" ? "primary" : "warn"}
          icon={icon[a]}
          disabled={!allowed || mutation.isPending}
          title={!allowed ? deniedReason("mission.control") : undefined}
          onClick={() => {
            mutation.reset();
            setReason(`${a} requested from dashboard`);
            setAction(a);
          }}
        >
          {a[0]!.toUpperCase() + a.slice(1)}
        </Button>
      ))}
      {!allowed && actions.length > 0 && (
        <span className="xs muted">Lifecycle control requires the mission coordinator role.</span>
      )}
      {provider.mode === "synthetic" && <SyntheticPlayback missionId={mission.id} />}
      <ConfirmDialog
        open={action !== null}
        title={`${action ?? ""} mission “${mission.name}”?`}
        confirmLabel={`Confirm ${action ?? ""}`}
        tone={action === "stop" ? "bad" : "primary"}
        busy={mutation.isPending}
        disabled={!reason.trim()}
        onCancel={() => setAction(null)}
        onConfirm={() =>
          action &&
          mutation.mutate(
            { action, reason: reason.trim().slice(0, 100) },
            { onSuccess: () => setAction(null) },
          )
        }
      >
        {action && <p>{CONSEQUENCE[action]}</p>}
        <p className="xs muted">This controls the simulation only. It never commands a physical drone.</p>
        <TextField
          label="Reason (recorded in the audit log)"
          value={reason}
          onChange={setReason}
          required
          maxLength={100}
        />
        {mutation.isError && (
          <AlertBox tone="bad" title="Refused.">
            {asApiError(mutation.error).userMessage}
          </AlertBox>
        )}
      </ConfirmDialog>
    </div>
  );
}

function SyntheticPlayback({ missionId }: { missionId: string }) {
  const provider = useProvider();
  const controls = syntheticControls(provider);
  const { playbackSpeed, update } = usePreferences();
  const client = useQueryClient();
  if (!controls) return null;
  const refresh = () => void client.invalidateQueries({ queryKey: ["synthetic"] });
  return (
    <div className="row" role="group" aria-label="Synthetic playback">
      <label className="xs muted" htmlFor="speed">
        Playback
      </label>
      <select
        id="speed"
        value={playbackSpeed}
        onChange={(e) => {
          const v = Number(e.target.value);
          update({ playbackSpeed: v });
          controls.setSpeed(v);
        }}
      >
        {[0.5, 1, 2, 4, 8].map((v) => (
          <option key={v} value={v}>
            {v}×
          </option>
        ))}
      </select>
      <Button
        size="sm"
        icon={<SkipForward size={13} aria-hidden="true" />}
        onClick={() => {
          controls.advance(1);
          refresh();
        }}
      >
        Step
      </Button>
      <Button
        size="sm"
        icon={<RotateCcw size={13} aria-hidden="true" />}
        onClick={() => {
          controls.resetMission(missionId);
          refresh();
        }}
      >
        Reset demo
      </Button>
    </div>
  );
}
