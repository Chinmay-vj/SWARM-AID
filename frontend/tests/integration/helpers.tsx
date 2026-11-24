import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AppRoutes, Providers, createQueryClient } from "../../src/app/App";
import { setProvidersForTesting } from "../../src/services/providers";
import type { DataProvider } from "../../src/services/providers/types";
import { SyntheticProvider } from "../../src/services/providers/synthetic/provider";
import { useActivity } from "../../src/stores/activity";
import { useConnection } from "../../src/stores/connection";
import { useSession } from "../../src/stores/session";
import { useMissionStore } from "../../src/features/missions/missionContext";
import type { Me } from "../../src/contracts/api";

export function resetStores(mode: "connected" | "synthetic" = "synthetic") {
  useSession.setState({ mode, me: null, status: "anonymous", expiredNotice: null });
  useActivity.setState({ missionId: null, events: [], notifications: [] });
  useConnection.getState().reset();
  useConnection.setState({ backend: "unknown", samples: [] });
  useMissionStore.setState({ value: null });
}

export function renderApp(path: string) {
  const client = createQueryClient();
  const utils = render(
    <Providers client={client}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </Providers>,
  );
  return { ...utils, client };
}

export async function syntheticSession(
  role: "coordinator" | "operator" | "observer" | "researcher" = "coordinator",
) {
  const provider = new SyntheticProvider({ tickIntervalMs: 1_000_000 });
  provider.setRole(role);
  setProvidersForTesting({ synthetic: provider });
  resetStores("synthetic");
  const me = await provider.login("demo", "");
  useSession.getState().signedIn(me);
  return provider;
}

/** A connected provider stub: every method rejects unless overridden. */
export function connectedStub(overrides: Partial<DataProvider>, me: Me): DataProvider {
  const reject = () => Promise.reject(new Error("not stubbed"));
  const base = new Proxy({} as Record<string, unknown>, {
    get: (_t, prop) => {
      if (prop in overrides) return (overrides as Record<string, unknown>)[prop as string];
      if (prop === "mode") return "connected";
      if (prop === "sourceLabel") return "Connected (test stub)";
      if (prop === "subscribe")
        return (_m: string, _a: number, h: { onStatus: (s: string) => void }) => (
          h.onStatus("open"), { close: () => undefined, reconnect: () => undefined }
        );
      if (prop === "probe") return async () => ({ live: true, ready: true });
      if (prop === "me") return async () => me;
      return reject;
    },
  });
  return base as unknown as DataProvider;
}
