import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  COMMAND_MODES,
  COORDINATION_POLICIES,
  MISSION_STATUSES,
  MissionConfigSchema,
  type Mission,
  type MissionConfig,
} from "../../contracts/api";
import { DataTable, Pagination, SelectField, TextField, type Column } from "../../components/ui/data";
import { Modal } from "../../components/ui/dialogs";
import { Button, PageHeader, Panel, SourceTag, StatusBadge } from "../../components/ui/primitives";
import { AlertBox, EmptyState, QueryView } from "../../components/ui/states";
import { keys, useMode, useProvider, useProviderQuery, useMissionMutation } from "../../hooks/data";
import { formatSimTime, formatWallTime, humanize } from "../../lib/format";
import { canCreateMissions } from "../../lib/permissions";
import { developmentSeedError } from "../../lib/seeds";
import { asApiError } from "../../services/api/errors";
import { usePreferences } from "../../stores/preferences";
import { useSession } from "../../stores/session";

const PAGE = 25;

export default function MissionsPage() {
  const mode = useMode();
  const me = useSession((s) => s.me);
  const navigate = useNavigate();
  const timeDisplay = usePreferences((s) => s.timeDisplay);
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState(false);
  const missions = useProviderQuery(
    [...keys.missions(mode), status, offset],
    (p, s) => p.missions({ status: status || undefined, limit: PAGE, offset }, s),
    { refetchInterval: 10_000 },
  );

  const columns = useMemo<Column<Mission>[]>(
    () => [
      {
        key: "name",
        header: "Mission",
        cell: (m) => <Link to={`/missions/${m.id}/overview`}>{m.name}</Link>,
        sort: (m) => m.name.toLowerCase(),
      },
      { key: "scenario", header: "Scenario", cell: (m) => m.scenario_id, sort: (m) => m.scenario_id },
      {
        key: "status",
        header: "Status",
        cell: (m) => <StatusBadge status={m.status} />,
        sort: (m) => m.status,
      },
      { key: "agents", header: "Agents", cell: (m) => String(m.config.agents ?? "—") },
      { key: "seed", header: "Seed", cell: (m) => String(m.config.seed ?? "—") },
      { key: "policy", header: "Coordination", cell: (m) => humanize(String(m.config.coordination ?? "")) },
      {
        key: "sim",
        header: "Sim time",
        cell: (m) => <span className="mono">{formatSimTime(m.last_sim_ms)}</span>,
        sort: (m) => m.last_sim_ms,
      },
      {
        key: "created",
        header: "Created",
        cell: (m) => formatWallTime(m.created_at, timeDisplay),
        sort: (m) => m.created_at,
      },
    ],
    [timeDisplay],
  );

  return (
    <div className="stack">
      <PageHeader
        title="Missions"
        description={
          mode === "synthetic"
            ? "Synthetic demonstration presets (fixed). Select one to open its dashboard."
            : "Missions you are a member of. Administrators see all missions."
        }
        actions={
          mode === "connected" &&
          canCreateMissions(me) && (
            <Button
              variant="primary"
              icon={<Plus size={15} aria-hidden="true" />}
              onClick={() => setCreating(true)}
            >
              New mission
            </Button>
          )
        }
      />
      <Panel title="Mission list" actions={<SourceTag synthetic={mode === "synthetic"} />}>
        <div className="filters" style={{ marginBottom: 8 }}>
          <SelectField
            label="Status"
            value={status}
            onChange={(v) => {
              setStatus(v);
              setOffset(0);
            }}
            options={["", ...MISSION_STATUSES]}
          />
        </div>
        <QueryView query={missions} rows={6}>
          {(data) => (
            <>
              <DataTable
                caption="Missions"
                rows={data.items}
                columns={columns}
                rowKey={(m) => m.id}
                onSelect={(m) => navigate(`/missions/${m.id}/overview`)}
                empty={
                  <EmptyState title="No missions">
                    {mode === "connected" && canCreateMissions(me)
                      ? "Create a mission to start a simulation."
                      : "Ask a coordinator to add you to a mission."}
                  </EmptyState>
                }
              />
              <Pagination total={data.total} limit={PAGE} offset={offset} onChange={setOffset} />
            </>
          )}
        </QueryView>
      </Panel>
      {creating && (
        <CreateMissionDialog
          onClose={() => setCreating(false)}
          onCreated={(m) => navigate(`/missions/${m.id}/overview`)}
        />
      )}
    </div>
  );
}

function CreateMissionDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (m: Mission) => void;
}) {
  const mode = useMode();
  const scenarios = useProviderQuery(keys.global(mode, "scenarios"), (p, s) => p.scenarios(s), {
    staleTime: 60_000,
  });
  const [name, setName] = useState("Six-agent flood");
  const [description, setDescription] = useState("");
  const [scenario, setScenario] = useState("flood_basic");
  const [agents, setAgents] = useState("6");
  const [seed, setSeed] = useState("");
  const [horizon, setHorizon] = useState("");
  const [coordination, setCoordination] = useState<MissionConfig["coordination"]>("shared_information");
  const [command, setCommand] = useState<MissionConfig["command_mode"]>("fusion");
  const [error, setError] = useState<string | null>(null);
  const provider = useProvider();
  const create = useMissionMutation(
    undefined,
    (p, body: { name: string; description: string; config: MissionConfig }) => p.createMission(body),
  );
  const info = scenarios.data?.find((s) => s.scenario_id === scenario);

  const submit = () => {
    setError(null);
    const seedError = developmentSeedError(seed);
    if (seedError) return setError(seedError);
    const config = {
      scenario_id: scenario,
      agents: Number(agents),
      seed: Number(seed),
      horizon: horizon ? Number(horizon) : null,
      coordination,
      command_mode: command,
    };
    const parsed = MissionConfigSchema.safeParse(config);
    if (!parsed.success) {
      setError(parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; "));
      return;
    }
    if (!name.trim()) return setError("Name is required.");
    create.mutate(
      { name: name.trim(), description, config: parsed.data },
      {
        onSuccess: async (mission) => {
          // The backend grants the creator the coordinator role on the new mission.
          try {
            useSession.getState().signedIn(await provider.me());
          } catch {
            /* MissionLayout refreshes the identity as well */
          }
          onCreated(mission);
        },
      },
    );
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="New simulation mission"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={submit} disabled={create.isPending}>
            {create.isPending ? "Creating…" : "Create mission"}
          </Button>
        </>
      }
    >
      <p className="xs muted">
        The mission is created in draft state. Start it from its overview. The backend validates the
        configuration against the scenario fixtures.
      </p>
      <TextField label="Name" value={name} onChange={setName} required maxLength={128} />
      <TextField
        label="Description"
        value={description}
        onChange={setDescription}
        maxLength={2000}
        multiline
      />
      <QueryView query={scenarios} rows={2}>
        {(list) => (
          <SelectField
            label="Scenario"
            value={scenario}
            onChange={(v) => {
              setScenario(v);
            }}
            options={list.map((s) => ({
              value: s.scenario_id,
              label: `${s.scenario_id} · ${s.disaster}${s.faults.length ? ` · ${s.faults.join(", ")}` : ""}`,
            }))}
            help={
              info
                ? `${info.width}×${info.height} cells · default ${info.default_agents} agents · horizon ${info.horizon} ticks of ${info.tick_ms} ms · modalities ${info.modalities.join(", ")}`
                : undefined
            }
          />
        )}
      </QueryView>
      <div className="grid cols-3">
        <TextField label="Agents (1–20)" type="number" value={agents} onChange={setAgents} min={1} max={20} />
        <TextField
          label="Seed"
          type="number"
          value={seed}
          onChange={setSeed}
          min={12000}
          max={12999}
          help="Required: a development seed, 12000–12999"
        />
        <TextField
          label="Horizon (ticks)"
          type="number"
          value={horizon}
          onChange={setHorizon}
          min={1}
          max={5000}
          help="Empty = scenario default"
        />
      </div>
      <div className="grid cols-2">
        <SelectField
          label="Coordination policy"
          value={coordination}
          onChange={(v) => setCoordination(v as MissionConfig["coordination"])}
          options={COORDINATION_POLICIES.map((v) => ({ value: v, label: humanize(v) }))}
        />
        <SelectField
          label="Model 2 mode"
          value={command}
          onChange={(v) => setCommand(v as MissionConfig["command_mode"])}
          options={COMMAND_MODES.map((v) => ({
            value: v,
            label:
              v === "fusion"
                ? "fusion (multi-agent evidence fusion)"
                : v === "rules"
                  ? "rules (individual rule-based assessment)"
                  : "direct (report forwarding)",
          }))}
        />
      </div>
      {(error || create.isError) && (
        <AlertBox tone="bad">{error ?? asApiError(create.error).userMessage}</AlertBox>
      )}
    </Modal>
  );
}
