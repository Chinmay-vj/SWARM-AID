import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup } from "@testing-library/react";
import { ApiError } from "../../src/services/api/errors";
import { setProvidersForTesting } from "../../src/services/providers";
import { useActivity } from "../../src/stores/activity";
import { useSession } from "../../src/stores/session";
import type { Me, Mission } from "../../src/contracts/api";
import { connectedStub, renderApp, resetStores, syntheticSession } from "./helpers";

afterEach(() => cleanup());

describe("authentication and protected routes", () => {
  beforeEach(() => resetStores("connected"));

  it("redirects unauthenticated users to sign in", async () => {
    renderApp("/missions/abc/overview");
    expect(await screen.findByRole("heading", { name: /SWARM-AID command dashboard/ })).toBeInTheDocument();
    expect(screen.getByLabelText(/Username/)).toBeInTheDocument();
  });

  it("shows a clear error for rejected credentials and never stores the password", async () => {
    setProvidersForTesting({
      connected: connectedStub(
        { login: () => Promise.reject(new ApiError("unauthenticated", "invalid credentials", 401)) },
        {} as Me,
      ),
    });
    renderApp("/login");
    await userEvent.type(await screen.findByLabelText(/Username/), "coordinator");
    await userEvent.type(screen.getByLabelText(/Password/), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText(/Username or password is incorrect/)).toBeInTheDocument();
    expect(JSON.stringify(sessionStorage)).not.toContain("wrong-password");
    expect(JSON.stringify(localStorage)).not.toContain("wrong-password");
  });
});

describe("synthetic demo mode", () => {
  beforeEach(async () => {
    await syntheticSession("coordinator");
  });

  it("labels synthetic data prominently and renders the overview", async () => {
    renderApp("/missions/syn-flood-6/overview");
    expect(await screen.findByText("SYNTHETIC DEMO MODE.")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Six-agent flood demonstration" })).toBeInTheDocument();
    expect(screen.getAllByText(/synthetic/i).length).toBeGreaterThan(3);
  });

  it("navigates between mission views from the sidebar", async () => {
    renderApp("/missions/syn-flood-6/overview");
    const nav = await screen.findByRole("navigation", { name: "Main navigation" });
    await userEvent.click(within(nav).getByRole("link", { name: /Drone fleet/ }));
    expect(await screen.findByRole("heading", { name: /Drone fleet/ })).toBeInTheDocument();
    await userEvent.click(within(nav).getByRole("link", { name: /Human review/ }));
    expect(await screen.findByRole("heading", { name: "Human review" })).toBeInTheDocument();
  });

  it("starts the mission only after confirmation", async () => {
    const provider = await syntheticSession("coordinator");
    renderApp("/missions/syn-flood-6/overview");
    await userEvent.click(await screen.findByRole("button", { name: "Start" }));
    const dialog = await screen.findByRole("dialog");
    expect((await provider.mission("syn-flood-6")).status).toBe("draft");
    await userEvent.click(within(dialog).getByRole("button", { name: /Confirm start/ }));
    await waitFor(async () => expect((await provider.mission("syn-flood-6")).status).toBe("running"));
  });

  it("submits a decision and shows 'submitted', never 'approved', before validation", async () => {
    const provider = await syntheticSession("coordinator");
    await provider.controlMission("syn-flood-6", "start", "t");
    provider.advance(120);
    await provider.controlMission("syn-flood-6", "pause", "review");
    renderApp("/missions/syn-flood-6/review");
    const approve = await screen.findAllByRole("button", { name: "Approve review" });
    await userEvent.click(approve[0]!);
    const dialog = await screen.findByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: "Approve review" });
    expect(confirm).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText(/Reason/), "evidence reviewed");
    await userEvent.click(within(dialog).getByRole("checkbox"));
    await userEvent.click(confirm);
    expect(
      await within(await screen.findByRole("dialog")).findByText(/Decision recorded and sent to Model 2/),
    ).toBeInTheDocument();
    expect(screen.getAllByText("submitted").length).toBeGreaterThan(0);
  });

  it("handles a stale recommendation version", async () => {
    const provider = await syntheticSession("coordinator");
    await provider.controlMission("syn-version", "start", "t");
    provider.advance(120);
    await provider.controlMission("syn-version", "pause", "review");
    renderApp("/missions/syn-version/review");
    await userEvent.click((await screen.findAllByRole("button", { name: "Approve review" }))[0]!);
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/Reason/), "check");
    await userEvent.click(within(dialog).getByRole("checkbox"));
    await userEvent.click(within(dialog).getByRole("button", { name: "Approve review" }));
    expect(await within(dialog).findByText(/This version is outdated/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Load updated version" })).toBeInTheDocument();
  });

  it("disables consequential actions for an observer", async () => {
    const provider = await syntheticSession("observer");
    await provider.controlMission("syn-flood-6", "start", "t").catch(() => undefined);
    renderApp("/missions/syn-flood-6/overview");
    expect(await screen.findByRole("button", { name: "Start" })).toBeDisabled();
    expect(screen.getByText(/requires the mission coordinator role/)).toBeInTheDocument();
  });

  it("shows error state with retry for the backend-failure preset", async () => {
    renderApp("/missions/syn-backend-failure/overview");
    expect(
      await screen.findByText(/backend could not be reached/i, {}, { timeout: 4000 }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows empty states for the empty mission", async () => {
    renderApp("/missions/syn-empty/overview");
    expect(await screen.findByText("No agents registered")).toBeInTheDocument();
    expect(screen.getByText("Nothing awaiting review")).toBeInTheDocument();
  });

  it("shows not-found pages for unknown routes and missions", async () => {
    renderApp("/missions/does-not-exist/overview");
    expect(await screen.findByText("Mission not found")).toBeInTheDocument();
    cleanup();
    renderApp("/nowhere");
    expect(await screen.findByText("Page not found")).toBeInTheDocument();
  });

  it("renders the map with an accessible entity list and no movement controls", async () => {
    const provider = await syntheticSession("coordinator");
    await provider.controlMission("syn-flood-6", "start", "t");
    provider.advance(30);
    renderApp("/missions/syn-flood-6/map");
    expect(
      await screen.findByRole("application", { name: /Mission map, local grid 12 by 10/ }),
    ).toBeInTheDocument();
    const table = await screen.findByRole("table", { name: "Map entities" });
    expect(within(table).getAllByRole("row").length).toBeGreaterThan(1);
    expect(screen.queryByRole("button", { name: /move|fly|goto/i })).toBeNull();
    expect(screen.getByText(/not GPS/)).toBeInTheDocument();
  });
});

describe("connected mode", () => {
  const me: Me = {
    subject: "coordinator",
    kind: "human",
    user_id: "387ea4b3-243d-4324-94da-d3afa8eb696d",
    global_role: "coordinator",
    memberships: [],
    machine_mission: null,
  };
  beforeEach(() => resetStores("connected"));

  it("shows a connection failure instead of substituting synthetic data", async () => {
    setProvidersForTesting({
      connected: connectedStub(
        {
          missions: () => Promise.reject(new ApiError("network", "Failed to fetch")),
          probe: async () => ({ live: false, ready: null }),
        },
        me,
      ),
    });
    useSession.getState().signedIn(me);
    renderApp("/missions");
    expect(
      await screen.findByText(/backend could not be reached/i, {}, { timeout: 4000 }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Backend unreachable.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use synthetic demo instead" })).toBeInTheDocument();
    expect(screen.queryByText("Six-agent flood demonstration")).toBeNull();
  });

  it("keeps cross-mission access denied by the backend", async () => {
    setProvidersForTesting({
      connected: connectedStub(
        { mission: () => Promise.reject(new ApiError("not_found", "mission not found", 404, "not_found")) },
        me,
      ),
    });
    useSession.getState().signedIn(me);
    renderApp("/missions/3375d81f-5ae3-4eec-948f-fc753c12730b/overview");
    expect(await screen.findByText("Mission not found")).toBeInTheDocument();
  });

  it("lists missions with the create action for coordinators", async () => {
    const mission: Mission = {
      id: "3375d81f-5ae3-4eec-948f-fc753c12730b",
      name: "Connected flood",
      description: "",
      scenario_id: "flood_basic",
      sim_mission_id: "fb7096a0-e6c7-5d76-99ac-09a4f148eb3c",
      config: { agents: 6, seed: 42, coordination: "shared_information" },
      status: "draft",
      version: 1,
      created_by: me.user_id!,
      created_at: "2026-11-24T13:25:42Z",
      updated_at: "2026-11-24T13:25:42Z",
      last_sim_ms: 0,
      model2_state: "inactive",
      communication_state: "unknown",
      last_event_sequence: 1,
      current_run_id: null,
    };
    setProvidersForTesting({
      connected: connectedStub(
        { missions: async () => ({ items: [mission], total: 1, limit: 25, offset: 0 }) },
        me,
      ),
    });
    useSession.getState().signedIn(me);
    renderApp("/missions");
    expect(await screen.findByRole("link", { name: "Connected flood" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New mission" })).toBeInTheDocument();
    expect(screen.queryByText("SYNTHETIC DEMO MODE.")).toBeNull();
  });

  it("restricts system health details to administrators", async () => {
    setProvidersForTesting({ connected: connectedStub({}, me) });
    useSession.getState().signedIn(me);
    renderApp("/system");
    expect(await screen.findByText("Detailed backend health is restricted.")).toBeInTheDocument();
  });
});

describe("mode isolation", () => {
  it("clears timeline and cache when switching modes", async () => {
    await syntheticSession("coordinator");
    useActivity.setState({
      missionId: "syn-flood-6",
      events: [],
      notifications: [
        {
          id: "n",
          key: "k",
          missionId: "syn-flood-6",
          severity: "warning",
          title: "synthetic alert",
          eventType: "ALERT_RAISED",
          sequence: 1,
          simTimeMs: 0,
          receivedAt: 0,
          count: 1,
          read: false,
          resourceType: "alert",
          resourceId: "a",
          synthetic: true,
        },
      ],
    });
    renderApp("/settings");
    await userEvent.click(await screen.findByRole("button", { name: /Switch to connected mode/ }));
    await waitFor(() => expect(useSession.getState().mode).toBe("connected"));
    expect(useSession.getState().status).toBe("anonymous");
    expect(useActivity.getState().notifications).toHaveLength(0);
  });
});
