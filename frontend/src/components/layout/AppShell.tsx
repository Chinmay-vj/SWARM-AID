import {
  Activity,
  BarChart3,
  Bell,
  Bot,
  BrainCircuit,
  ClipboardCheck,
  FileSearch,
  FlaskConical,
  HeartPulse,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Map as MapIcon,
  Menu,
  Moon,
  Network,
  Settings,
  ShieldAlert,
  Siren,
  Sun,
  Telescope,
  Waves,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation, useMatch, useNavigate } from "react-router-dom";
import { eventResourcePath } from "../../contracts/events";
import { useMissionPermissions, useMode, useProvider } from "../../hooks/data";
import { useAuthActions } from "../../hooks/useAuthActions";
import { formatSimTime } from "../../lib/format";
import { canReadExperiments, canReadSystemHealth, missionRole } from "../../lib/permissions";
import { statusLabel } from "../../lib/status";
import { useActivity } from "../../stores/activity";
import { useConnection } from "../../stores/connection";
import { usePreferences } from "../../stores/preferences";
import { useSession } from "../../stores/session";
import { useMissionContext } from "../../features/missions/missionContext";
import { Drawer } from "../ui/dialogs";
import { Button, StatusBadge } from "../ui/primitives";
import { EmptyState } from "../ui/states";

function useBackendProbe() {
  const provider = useProvider();
  const setBackend = useConnection((s) => s.setBackend);
  useEffect(() => {
    if (provider.mode !== "connected") return;
    const controller = new AbortController();
    const run = () =>
      provider
        .probe(controller.signal)
        .then((p) => setBackend(!p.live ? "offline" : p.ready === false ? "not_ready" : "online"))
        .catch(() => undefined);
    run();
    const timer = setInterval(run, 10_000);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [provider, setBackend]);
}

function TopBar({ onMenu }: { onMenu: () => void }) {
  const mode = useMode();
  const me = useSession((s) => s.me);
  const ctx = useMissionContext();
  const backend = useConnection((s) => s.backend);
  const stream = useConnection((s) => s.stream);
  const { theme, update } = usePreferences();
  const { logout } = useAuthActions();
  const [notifOpen, setNotifOpen] = useState(false);
  const unread = useActivity((s) => s.notifications.filter((n) => !n.read).length);
  const mission = ctx?.mission;
  const role = mission ? missionRole(me, mission.id) : null;
  const backendTone =
    mode === "synthetic"
      ? "muted"
      : backend === "online"
        ? "ok"
        : backend === "not_ready"
          ? "warn"
          : backend === "offline"
            ? "bad"
            : "muted";

  return (
    <header className="topbar">
      <Button
        className="menu-button"
        variant="ghost"
        aria-label="Open navigation"
        icon={<Menu size={18} aria-hidden="true" />}
        onClick={onMenu}
      />
      <Link to="/missions" className="brand" aria-label="SWARM-AID missions">
        <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">
          <circle cx="16" cy="16" r="5" fill="none" stroke="var(--accent)" strokeWidth="2" />
          <path d="M16 3v6M16 23v6M3 16h6M23 16h6" stroke="var(--accent)" strokeWidth="2" />
          <circle cx="16" cy="16" r="13" fill="none" stroke="var(--accent)" strokeOpacity=".35" />
        </svg>
        <span>
          <b>SWARM-AID</b>
          <small>Rescue command dashboard · simulation research</small>
        </span>
      </Link>
      <div className="topbar-status" aria-label="System status">
        <div className="tstat">
          <span>Data source</span>
          <b>
            <StatusBadge
              status={mode}
              tone={mode === "synthetic" ? "warn" : "ok"}
              label={mode === "synthetic" ? "Synthetic demo" : "Connected"}
            />
          </b>
        </div>
        <div className="tstat">
          <span>Mission</span>
          <b title={mission?.name}>
            {mission ? (
              <Link to={`/missions/${mission.id}/overview`}>
                {mission.name.length > 26 ? `${mission.name.slice(0, 25)}…` : mission.name}
              </Link>
            ) : (
              <span className="muted">none selected</span>
            )}
          </b>
        </div>
        {mission && (
          <>
            <div className="tstat">
              <span>Status</span>
              <b>
                <StatusBadge status={mission.status} />
              </b>
            </div>
            <div className="tstat optional">
              <span>Sim time</span>
              <b className="mono">{formatSimTime(mission.last_sim_ms)}</b>
            </div>
            <div className="tstat optional">
              <span>Model 2</span>
              <b>
                <StatusBadge status={mission.model2_state} />
              </b>
            </div>
            <div className="tstat optional">
              <span>Comms</span>
              <b>
                <StatusBadge status={mission.communication_state} />
              </b>
            </div>
          </>
        )}
        <div className="tstat">
          <span>Backend</span>
          <b>
            <StatusBadge
              status={backend}
              tone={backendTone}
              label={mode === "synthetic" ? "not used" : statusLabel(backend)}
            />
          </b>
        </div>
        {mission && (
          <div className="tstat optional">
            <span>Live events</span>
            <b>
              <StatusBadge
                status={stream}
                tone={
                  stream === "open"
                    ? "ok"
                    : stream === "polling" || stream === "reconnecting" || stream === "connecting"
                      ? "warn"
                      : stream === "failed"
                        ? "bad"
                        : "muted"
                }
                label={stream}
              />
            </b>
          </div>
        )}
      </div>
      <div className="topbar-actions">
        <Button
          variant="ghost"
          aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
          onClick={() => setNotifOpen(true)}
          icon={<Bell size={17} aria-hidden="true" />}
        >
          {unread > 0 && <span className="badge tone-warn">{unread > 99 ? "99+" : unread}</span>}
        </Button>
        <Button
          variant="ghost"
          aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
          icon={
            theme === "light" ? <Moon size={17} aria-hidden="true" /> : <Sun size={17} aria-hidden="true" />
          }
          onClick={() => update({ theme: theme === "light" ? "dark" : "light" })}
        />
        <div className="tstat optional" style={{ textAlign: "right" }}>
          <span>{me?.subject ?? "—"}</span>
          <b className="xs">
            {me?.global_role ?? "no role"}
            {role ? ` · mission ${role}` : ""}
          </b>
        </div>
        <Button
          variant="ghost"
          aria-label="Sign out"
          icon={<LogOut size={17} aria-hidden="true" />}
          onClick={() => void logout()}
        />
      </div>
      <NotificationsDrawer open={notifOpen} onClose={() => setNotifOpen(false)} />
    </header>
  );
}

function NotificationsDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { notifications, markRead } = useActivity();
  const navigate = useNavigate();
  const [filter, setFilter] = useState<"all" | "critical" | "warning">("all");
  const timeDisplay = usePreferences((s) => s.timeDisplay);
  const shown = notifications.filter((n) => filter === "all" || n.severity === filter);
  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="Notifications"
      actions={
        <Button size="sm" onClick={() => markRead()}>
          Mark all read
        </Button>
      }
    >
      <p className="xs muted">
        Local notifications from this browser's event stream. Backend alerts are acknowledged on the Human
        Review page.
      </p>
      <div className="row" role="group" aria-label="Severity filter">
        {(["all", "critical", "warning"] as const).map((f) => (
          <Button
            key={f}
            size="sm"
            variant={filter === f ? "primary" : "default"}
            aria-pressed={filter === f}
            onClick={() => setFilter(f)}
          >
            {f}
          </Button>
        ))}
      </div>
      {shown.length === 0 ? (
        <EmptyState title="No notifications" />
      ) : (
        <ul className="timeline" aria-label="Notification history">
          {shown.map((n) => {
            const path = eventResourcePath(n.missionId, {
              resource_type: n.resourceType,
              resource_id: n.resourceId,
              payload: {},
            });
            return (
              <li key={n.id} style={{ opacity: n.read ? 0.7 : 1 }}>
                <span className="t">
                  {formatSimTime(n.simTimeMs)}
                  <br />
                  {timeDisplay === "utc"
                    ? new Date(n.receivedAt).toISOString().slice(11, 19)
                    : new Date(n.receivedAt).toLocaleTimeString()}
                </span>
                <div className="stack tight">
                  <div className="row">
                    <StatusBadge
                      status={n.severity}
                      tone={
                        n.severity === "critical"
                          ? "bad"
                          : n.severity === "warning"
                            ? "warn"
                            : n.severity === "success"
                              ? "ok"
                              : "info"
                      }
                      label={n.severity}
                    />
                    {n.synthetic && <span className="source-tag">Synthetic</span>}
                    {n.count > 1 && <span className="xs muted">×{n.count}</span>}
                    {!n.read && <span className="sr-only">unread</span>}
                  </div>
                  <span>{n.title}</span>
                  <div className="row">
                    {path && (
                      <Button
                        size="sm"
                        onClick={() => {
                          markRead(n.id);
                          onClose();
                          navigate(path);
                        }}
                      >
                        Open
                      </Button>
                    )}
                    {!n.read && (
                      <Button size="sm" variant="ghost" onClick={() => markRead(n.id)}>
                        Acknowledge
                      </Button>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Drawer>
  );
}

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  count?: number;
}

function Sidebar({ onNavigate }: { onNavigate: () => void }) {
  const match = useMatch("/missions/:missionId/*");
  const missionId = match?.params.missionId;
  const me = useSession((s) => s.me);
  const mode = useMode();
  const perms = useMissionPermissions(missionId);
  const ctx = useMissionContext();
  const pending = ctx?.pendingReviews ?? 0;
  const i = (C: typeof Activity) => <C size={16} aria-hidden="true" />;
  const mission: NavItem[] = missionId
    ? [
        { to: "overview", label: "Mission overview", icon: i(LayoutDashboard) },
        { to: "map", label: "Live simulation map", icon: i(MapIcon) },
        { to: "fleet", label: "Drone fleet (Model 1)", icon: i(Bot) },
        { to: "observations", label: "Observations", icon: i(Telescope) },
        { to: "incidents", label: "Incidents", icon: i(Siren) },
        { to: "evidence", label: "Evidence center", icon: i(FileSearch) },
        { to: "model2", label: "Command agent (Model 2)", icon: i(BrainCircuit) },
        { to: "recommendations", label: "Recommendations", icon: i(ClipboardCheck) },
        { to: "review", label: "Human review", icon: i(ShieldAlert), count: pending },
        { to: "coordination", label: "Tasks & coordination", icon: i(ListChecks) },
        { to: "environment", label: "Environment & hazards", icon: i(Waves) },
        { to: "communication", label: "Communication network", icon: i(Network) },
        { to: "events", label: "Event timeline", icon: i(Activity) },
        ...(perms.has("metrics.read") || mode === "synthetic"
          ? [{ to: "analytics", label: "Research analytics", icon: i(BarChart3) }]
          : []),
      ]
    : [];
  return (
    <nav
      className="sidebar"
      aria-label="Main navigation"
      onClick={(e) => (e.target as HTMLElement).closest("a") && onNavigate()}
    >
      <NavLink to="/missions" end>
        <LayoutDashboard size={16} aria-hidden="true" /> Missions
      </NavLink>
      {missionId ? (
        <>
          <div className="section">Current mission</div>
          {mission.map((item) => (
            <NavLink key={item.to} to={`/missions/${missionId}/${item.to}`}>
              {item.icon}
              {item.label}
              {item.count ? (
                <span className="count" aria-label={`${item.count} pending`}>
                  {item.count}
                </span>
              ) : null}
            </NavLink>
          ))}
        </>
      ) : (
        <p className="xs muted" style={{ padding: "6px 10px" }}>
          Select a mission to see its views.
        </p>
      )}
      <div className="section">Research & system</div>
      {(canReadExperiments(me) || mode === "synthetic") && (
        <NavLink to="/experiments">
          <FlaskConical size={16} aria-hidden="true" /> Experiment results
        </NavLink>
      )}
      {(canReadSystemHealth(me) || mode === "connected") && (
        <NavLink to="/system">
          <HeartPulse size={16} aria-hidden="true" /> System health
        </NavLink>
      )}
      <NavLink to="/settings">
        <Settings size={16} aria-hidden="true" /> Settings
      </NavLink>
      <div className="sidefoot">
        Simulation only. No physical drone control. Human decisions remain authoritative; recommendations are
        decision support.
      </div>
    </nav>
  );
}

function ModeBanner() {
  const mode = useMode();
  const { switchMode } = useAuthActions();
  const backend = useConnection((s) => s.backend);
  const stream = useConnection((s) => s.stream);
  const detail = useConnection((s) => s.streamDetail);
  const ctx = useMissionContext();
  if (mode === "synthetic")
    return (
      <div className="mode-banner synthetic" role="status">
        <b>SYNTHETIC DEMO MODE.</b>
        <span>
          All data on screen is generated in this browser for demonstration. It is not measured, not stored,
          and decisions never reach the backend.
        </span>
        <Button size="sm" onClick={() => void switchMode("connected")}>
          Switch to connected mode
        </Button>
      </div>
    );
  if (backend === "offline" || backend === "not_ready")
    return (
      <div className="mode-banner failure" role="alert">
        <b>
          {backend === "offline" ? "Backend unreachable." : "Backend not ready (database or migrations)."}
        </b>
        <span>
          Values shown are the last data received and may be stale. No synthetic data is substituted.
        </span>
        <Button size="sm" onClick={() => void switchMode("synthetic")}>
          Use synthetic demo instead
        </Button>
      </div>
    );
  if (ctx && (stream === "failed" || stream === "polling" || stream === "reconnecting"))
    return (
      <div className="mode-banner failure" role="status">
        <b>Live event stream {stream}.</b>
        <span>
          {detail ?? ""}{" "}
          {stream === "polling" ? "Updates arrive by REST polling." : "Views refresh periodically."}
        </span>
        <Button size="sm" onClick={() => ctx.reconnect()}>
          Reconnect now
        </Button>
      </div>
    );
  return null;
}

function Toasts() {
  const notifications = useActivity((s) => s.notifications);
  const prefs = usePreferences((s) => s.notifications);
  const [visible, setVisible] = useState<string[]>([]);
  const [seen] = useState(() => new Set<string>());
  useEffect(() => {
    if (!prefs.enabled || !prefs.toasts) return;
    const rank = { info: 0, success: 0, warning: 1, critical: 2 } as const;
    const min = rank[prefs.minimum === "info" ? "info" : prefs.minimum];
    const fresh = notifications
      .filter((n) => !seen.has(`${n.id}:${n.count}`) && !n.read && rank[n.severity] >= min)
      .slice(0, 3);
    if (!fresh.length) return;
    fresh.forEach((n) => seen.add(`${n.id}:${n.count}`));
    setVisible((v) => [...fresh.map((n) => n.id), ...v].slice(0, 3));
    const timer = setTimeout(
      () => setVisible((v) => v.filter((id) => !fresh.some((n) => n.id === id))),
      6000,
    );
    return () => clearTimeout(timer);
  }, [notifications, prefs, seen]);
  const shown = notifications.filter((n) => visible.includes(n.id));
  return (
    <div className="toasts" aria-live="polite" aria-atomic="false">
      {shown.map((n) => (
        <div
          key={n.id}
          className={`toast tone-${n.severity === "critical" ? "bad" : n.severity === "warning" ? "warn" : "ok"}`}
        >
          {n.synthetic && <span className="source-tag">Synthetic</span>}
          <span>{n.title}</span>
        </div>
      ))}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [navOpen, setNavOpen] = useState(false);
  const location = useLocation();
  useBackendProbe();
  useEffect(() => setNavOpen(false), [location.pathname]);
  return (
    <div className={`shell ${navOpen ? "nav-open" : ""}`}>
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <TopBar onMenu={() => setNavOpen((v) => !v)} />
      <ModeBanner />
      <Sidebar onNavigate={() => setNavOpen(false)} />
      <main id="main" className="main" tabIndex={-1}>
        {children}
      </main>
      <Toasts />
    </div>
  );
}
