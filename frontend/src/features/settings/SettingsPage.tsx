import { LayerControls } from "../../components/maps/MissionMap";
import { SelectField } from "../../components/ui/data";
import { Button, PageHeader, Panel } from "../../components/ui/primitives";
import { usePreferences, type Density, type Theme } from "../../stores/preferences";
import type { TimeDisplay } from "../../lib/format";
import { useAuthActions } from "../../hooks/useAuthActions";
import { useMode } from "../../hooks/data";

export default function SettingsPage() {
  const p = usePreferences();
  const mode = useMode();
  const { switchMode } = useAuthActions();
  return (
    <div className="stack">
      <PageHeader
        title="Settings"
        description="Preferences are stored in this browser only. No credentials or mission records are stored."
      />
      <div className="grid cols-2">
        <Panel title="Display">
          <div className="stack">
            <SelectField
              label="Theme"
              value={p.theme}
              onChange={(v) => p.update({ theme: v as Theme })}
              options={[
                { value: "system", label: "Follow system" },
                { value: "dark", label: "Dark" },
                { value: "light", label: "Light" },
              ]}
            />
            <SelectField
              label="Table density"
              value={p.density}
              onChange={(v) => p.update({ density: v as Density })}
              options={["comfortable", "compact"]}
            />
            <SelectField
              label="Wall-clock time display"
              value={p.timeDisplay}
              onChange={(v) => p.update({ timeDisplay: v as TimeDisplay })}
              options={[
                { value: "local", label: "Local time" },
                { value: "utc", label: "UTC" },
              ]}
              help="Simulation time is always shown as T+mm:ss."
            />
          </div>
        </Panel>
        <Panel title="Accessibility">
          <div className="stack tight">
            <label className="check">
              <input
                type="checkbox"
                checked={p.reducedMotion}
                onChange={() => p.update({ reducedMotion: !p.reducedMotion })}
              />
              Reduce motion (disables pulses, transitions and marker interpolation)
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={p.largeText}
                onChange={() => p.update({ largeText: !p.largeText })}
              />
              Larger text
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={p.autoScrollTimeline}
                onChange={() => p.update({ autoScrollTimeline: !p.autoScrollTimeline })}
              />
              Live-update event timelines by default
            </label>
          </div>
        </Panel>
        <Panel title="Notifications">
          <div className="stack tight">
            <label className="check">
              <input
                type="checkbox"
                checked={p.notifications.enabled}
                onChange={() =>
                  p.update({ notifications: { ...p.notifications, enabled: !p.notifications.enabled } })
                }
              />
              Enable notifications
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={p.notifications.toasts}
                onChange={() =>
                  p.update({ notifications: { ...p.notifications, toasts: !p.notifications.toasts } })
                }
              />
              Show pop-up toasts
            </label>
            <SelectField
              label="Minimum toast severity"
              value={p.notifications.minimum}
              onChange={(v) =>
                p.update({
                  notifications: { ...p.notifications, minimum: v as "info" | "warning" | "critical" },
                })
              }
              options={["info", "warning", "critical"]}
            />
          </div>
        </Panel>
        <Panel title="Map">
          <LayerControls />
        </Panel>
        <Panel title="Synthetic playback">
          <SelectField
            label="Default playback speed"
            value={String(p.playbackSpeed)}
            onChange={(v) => p.update({ playbackSpeed: Number(v) })}
            options={["0.5", "1", "2", "4", "8"].map((v) => ({ value: v, label: `${v}×` }))}
          />
        </Panel>
        <Panel title="Data source">
          <p className="small">
            Current: {mode === "synthetic" ? "Synthetic demo" : "Connected backend"}. Switching signs you out
            and clears all cached data.
          </p>
          <div className="row" style={{ marginTop: 8 }}>
            <Button onClick={() => void switchMode(mode === "synthetic" ? "connected" : "synthetic")}>
              Switch to {mode === "synthetic" ? "connected" : "synthetic"} mode
            </Button>
            <Button variant="ghost" onClick={p.reset}>
              Reset preferences
            </Button>
          </div>
        </Panel>
      </div>
    </div>
  );
}
