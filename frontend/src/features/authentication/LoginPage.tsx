import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import type { MissionRole } from "../../contracts/api";
import { Button } from "../../components/ui/primitives";
import { SelectField, TextField } from "../../components/ui/data";
import { AlertBox } from "../../components/ui/states";
import { getProvider, syntheticControls } from "../../services/providers";
import { asApiError } from "../../services/api/errors";
import { safeRedirect } from "../../lib/redirect";
import { useActivity } from "../../stores/activity";
import { useSession } from "../../stores/session";
import { DEFAULT_SYNTHETIC_MISSION_ID } from "../missions/syntheticDefaults";

export default function LoginPage() {
  const { mode, setMode, status, signedIn, expiredNotice } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const client = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<MissionRole>("coordinator");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requested = (location.state as { from?: unknown } | null)?.from;
  const from = requested === undefined ? undefined : safeRedirect(requested);

  if (status === "authenticated") return <Navigate to={from ?? "/missions"} replace />;

  const choose = (next: "connected" | "synthetic") => {
    if (next === mode) return;
    client.clear();
    useActivity.getState().clear();
    setError(null);
    setMode(next);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const provider = getProvider(mode);
      syntheticControls(provider)?.setRole(role);
      const me = await provider.login(username.trim(), password);
      setPassword("");
      client.clear();
      signedIn(me);
      navigate(
        from ?? (mode === "synthetic" ? `/missions/${DEFAULT_SYNTHETIC_MISSION_ID}/overview` : "/missions"),
        { replace: true },
      );
    } catch (err) {
      const apiError = asApiError(err);
      setError(
        apiError.kind === "unauthenticated"
          ? "Username or password is incorrect, or the account is inactive."
          : apiError.kind === "rate_limited"
            ? "Too many sign-in attempts. Wait a minute and try again."
            : apiError.userMessage,
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="login">
      <div className="panel stack">
        <div>
          <h1>SWARM-AID command dashboard</h1>
          <p className="muted small">
            Civilian disaster search-and-rescue simulation research. No physical drone control. Human
            decisions remain authoritative.
          </p>
        </div>
        {expiredNotice && <AlertBox tone="warn">{expiredNotice}</AlertBox>}
        <fieldset className="stack tight" style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="field">
            <span className="label">Data source</span>
          </legend>
          <label className="check">
            <input
              type="radio"
              name="mode"
              checked={mode === "connected"}
              onChange={() => choose("connected")}
            />
            <span>
              <b>Connected simulation</b> — Phase 7 backend, persisted missions, live events
            </span>
          </label>
          <label className="check">
            <input
              type="radio"
              name="mode"
              checked={mode === "synthetic"}
              onChange={() => choose("synthetic")}
            />
            <span>
              <b>Synthetic demo</b> — deterministic in-browser playback, nothing is sent to the backend
            </span>
          </label>
        </fieldset>
        <form className="stack" onSubmit={(e) => void submit(e)} aria-label="Sign in">
          {mode === "connected" ? (
            <>
              <TextField
                label="Username"
                value={username}
                onChange={setUsername}
                required
                autoComplete="username"
                maxLength={64}
              />
              <TextField
                label="Password"
                type="password"
                value={password}
                onChange={setPassword}
                required
                autoComplete="current-password"
                maxLength={256}
              />
              <p className="xs muted">
                Accounts are created by an administrator (python -m backend.cli create-user). Passwords are
                never stored by the dashboard.
              </p>
            </>
          ) : (
            <>
              <SelectField
                label="Demonstration role"
                value={role}
                onChange={(v) => setRole(v as MissionRole)}
                options={[
                  { value: "coordinator", label: "Rescue coordinator (can decide)" },
                  { value: "operator", label: "Rescue operator" },
                  { value: "researcher", label: "Researcher" },
                  { value: "observer", label: "Observer (read only)" },
                ]}
                help="Synthetic accounts are separate from backend accounts. The same permission matrix applies."
              />
            </>
          )}
          {error && <AlertBox tone="bad">{error}</AlertBox>}
          <Button
            type="submit"
            variant="primary"
            disabled={busy || (mode === "connected" && (!username || !password))}
          >
            {busy ? "Signing in…" : mode === "connected" ? "Sign in" : "Start synthetic demo"}
          </Button>
        </form>
      </div>
    </main>
  );
}
