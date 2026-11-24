/**
 * Provider registry. Exactly one provider is active per session. Switching mode signs the user
 * out of the previous source and clears every cached query, so connected and synthetic data
 * can never mix.
 */
import { createConnectedProvider } from "../api/connected";
import { SyntheticProvider } from "./synthetic/provider";
import type { DataMode, DataProvider } from "./types";
import { recordApiSample } from "../../stores/connection";

let connected: ReturnType<typeof createConnectedProvider> | null = null;
let synthetic: SyntheticProvider | null = null;

export function getProvider(mode: DataMode): DataProvider {
  if (mode === "connected") {
    connected ??= createConnectedProvider({
      baseUrl: import.meta.env.VITE_API_BASE_URL || "",
      timeoutMs: Number(import.meta.env.VITE_API_TIMEOUT_MS) || 15000,
      observe: recordApiSample,
    });
    return connected;
  }
  synthetic ??= new SyntheticProvider();
  return synthetic;
}

/** Synthetic-only controls (playback speed, reset, demo role). Null in connected mode. */
export function syntheticControls(provider: DataProvider): SyntheticProvider | null {
  return provider instanceof SyntheticProvider ? provider : null;
}

/** For tests: replace providers. */
export function setProvidersForTesting(next: { connected?: DataProvider; synthetic?: DataProvider }): void {
  if (next.connected) connected = next.connected as ReturnType<typeof createConnectedProvider>;
  if (next.synthetic) synthetic = next.synthetic as SyntheticProvider;
}

export type { DataMode, DataProvider };
