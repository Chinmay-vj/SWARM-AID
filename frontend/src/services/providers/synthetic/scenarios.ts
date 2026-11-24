/**
 * Synthetic demonstration presets. Every value produced from these presets is labelled
 * SYNTHETIC in the UI and never reaches the backend or appears as a measured result.
 */
export interface SyntheticPreset {
  id: string;
  name: string;
  description: string;
  scenarioId: string;
  disaster: "flood" | "wildfire" | "earthquake";
  agents: number;
  seed: number;
  horizon: number;
  /** Ticks [start, end) during which the drone→command link is down. */
  outage?: [number, number];
  /** Ticks [start, end) during which Model 2 stops processing (reports queue). */
  model2Down?: [number, number];
  /** Inject low-confidence and contradicting reports. */
  conflict?: boolean;
  /** Agents (by index) whose thermal sensor is degraded. */
  missingThermal?: number[];
  /** The first human decision meets a concurrent Model 2 revision (stale version). */
  versionConflict?: boolean;
  /** Every read for this mission fails as if the backend were unreachable. */
  backendFailure?: boolean;
  /** Draft mission with no agents and no data. */
  empty?: boolean;
}

export const SYNTHETIC_PRESETS: SyntheticPreset[] = [
  {
    id: "syn-flood-6",
    name: "Six-agent flood demonstration",
    description:
      "Default demo: six Model 1 agents sweep sectors, a brief command-link outage, Model 2 fusion and human review.",
    scenarioId: "flood_basic",
    disaster: "flood",
    agents: 6,
    seed: 42,
    horizon: 160,
    outage: [52, 62],
  },
  {
    id: "syn-wildfire",
    name: "Wildfire search",
    description: "Fire-affected cells reported as hazards; six agents.",
    scenarioId: "wildfire_basic",
    disaster: "wildfire",
    agents: 6,
    seed: 7,
    horizon: 160,
  },
  {
    id: "syn-earthquake",
    name: "Earthquake search",
    description: "Structural damage and debris hazards; six agents.",
    scenarioId: "earthquake_basic",
    disaster: "earthquake",
    agents: 6,
    seed: 11,
    horizon: 160,
  },
  {
    id: "syn-conflict",
    name: "Conflicting evidence",
    description: "Low-confidence and contradicting reports produce incidents with conflicting observations.",
    scenarioId: "command_conflict",
    disaster: "flood",
    agents: 6,
    seed: 5,
    horizon: 160,
    conflict: true,
  },
  {
    id: "syn-comms",
    name: "Communication degradation",
    description: "Long command-link outage: positions go stale, reports queue and are delivered on recovery.",
    scenarioId: "flood_outage",
    disaster: "flood",
    agents: 6,
    seed: 42,
    horizon: 160,
    outage: [30, 75],
  },
  {
    id: "syn-model2-down",
    name: "Model 2 unavailable",
    description:
      "The command agent stops processing for a period; reports queue and assessments resume after recovery.",
    scenarioId: "flood_server_unavailable",
    disaster: "flood",
    agents: 6,
    seed: 42,
    horizon: 160,
    model2Down: [40, 80],
  },
  {
    id: "syn-modalities",
    name: "Missing modalities",
    description: "Two agents report a degraded thermal sensor; their evidence lacks thermal data.",
    scenarioId: "command_missing_modalities",
    disaster: "flood",
    agents: 6,
    seed: 3,
    horizon: 160,
    missingThermal: [1, 3],
  },
  {
    id: "syn-version",
    name: "Recommendation version conflict",
    description: "The first human decision races a new Model 2 revision and is rejected as stale.",
    scenarioId: "flood_multiple",
    disaster: "flood",
    agents: 6,
    seed: 42,
    horizon: 160,
    versionConflict: true,
  },
  {
    id: "syn-empty",
    name: "Empty mission",
    description: "A draft mission with no agents or reports, to show empty states.",
    scenarioId: "flood_basic",
    disaster: "flood",
    agents: 0,
    seed: 42,
    horizon: 40,
    empty: true,
  },
  {
    id: "syn-backend-failure",
    name: "Backend failure",
    description: "Every request fails as if the backend were unreachable, to show error and retry states.",
    scenarioId: "flood_basic",
    disaster: "flood",
    agents: 6,
    seed: 42,
    horizon: 160,
    backendFailure: true,
  },
];

export const DEFAULT_SYNTHETIC_MISSION = "syn-flood-6";
