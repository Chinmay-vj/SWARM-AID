import { useMemo } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import type { Hazard } from "../../contracts/api";
import { MissionMap } from "../../components/maps/MissionMap";
import { DataTable, type Column } from "../../components/ui/data";
import { Kv, PageHeader, Panel, SourceTag, StatusBadge } from "../../components/ui/primitives";
import { AlertBox, EmptyState, QueryView } from "../../components/ui/states";
import { useLiveInterval, useMissionQuery, useMode } from "../../hooks/data";
import { formatLocation, formatSimTime, humanize, shortId } from "../../lib/format";

export default function EnvironmentPage() {
  const { missionId } = useParams();
  const synthetic = useMode() === "synthetic";
  const live = useLiveInterval();
  const [params, setParams] = useSearchParams();
  const selected = params.get("hazard");
  const hazards = useMissionQuery(missionId, ["hazards"], (p, id, s) => p.hazards(id, s), {
    refetchInterval: live,
  });
  const env = useMissionQuery(missionId, ["environment"], (p, id, s) => p.environment(id, s), {
    refetchInterval: live,
  });
  const map = useMissionQuery(missionId, ["map"], (p, id, s) => p.map(id, s), { refetchInterval: live });
  const coverage = useMissionQuery(missionId, ["coverage"], (p, id, s) => p.coverage(id, s), {
    refetchInterval: live,
  });
  const hazardMap = useMemo(
    () =>
      map.data ? { ...map.data, layers: map.data.layers.filter((l) => l.name === "hazards") } : undefined,
    [map.data],
  );
  const current = hazards.data?.find((h) => h.id === selected);
  const select = (id: string) => setParams({ hazard: id }, { replace: true });

  const cols: Column<Hazard>[] = [
    { key: "id", header: "Hazard", cell: (h) => <code>{shortId(h.id)}</code> },
    { key: "l", header: "Category", cell: (h) => humanize(h.label), sort: (h) => h.label },
    { key: "loc", header: "Estimated location", cell: (h) => formatLocation(h.location) },
    { key: "n", header: "Reports", cell: (h) => h.report_count, sort: (h) => h.report_count },
    { key: "r", header: "Source agents", cell: (h) => h.reporters.join(", ") },
    {
      key: "f",
      header: "First reported",
      cell: (h) => <span className="mono">{formatSimTime(h.first_reported_ms)}</span>,
      sort: (h) => h.first_reported_ms,
    },
    {
      key: "u",
      header: "Last reported",
      cell: (h) => <span className="mono">{formatSimTime(h.last_reported_ms)}</span>,
      sort: (h) => h.last_reported_ms,
    },
    { key: "s", header: "Freshness", cell: (h) => <StatusBadge status={h.stale ? "stale" : "fresh"} /> },
  ];

  return (
    <div className="stack">
      <PageHeader
        title="Environment & hazards"
        description="Hazards reported by Model 1 agents (flooding, fire, structural damage, blocked or restricted areas). Severity is not reported by the backend and is not inferred."
        actions={<SourceTag synthetic={synthetic} />}
      />
      <AlertBox tone="warn" title="Absence of reported hazards does not mean an area is safe.">
        Unreported cells are unknown. The dashboard does not generate rescue routes.
      </AlertBox>
      <div className="grid main-side">
        <Panel title="Hazard overlay">
          <QueryView query={map}>
            {() =>
              hazardMap && (
                <MissionMap
                  data={hazardMap}
                  coverage={coverage.data}
                  selected={selected ? { layer: "hazards", id: selected } : null}
                  onSelect={(s) => select(s.id)}
                  height={380}
                  synthetic={synthetic}
                />
              )
            }
          </QueryView>
        </Panel>
        <Panel title="Hazard detail">
          {current ? (
            <Kv
              items={[
                ["Hazard ID", <code key="i">{current.id}</code>],
                ["Category", humanize(current.label)],
                ["Estimated location", formatLocation(current.location)],
                ["Reported severity", "not reported"],
                ["Report count", current.report_count],
                ["Source agents", current.reporters.join(", ")],
                [
                  "First / last report",
                  `${formatSimTime(current.first_reported_ms)} / ${formatSimTime(current.last_reported_ms)}`,
                ],
                ["Freshness", <StatusBadge key="f" status={current.stale ? "stale" : "fresh"} />],
                ["Review status", "Hazard incidents are reviewed on the Incidents page"],
              ]}
            />
          ) : (
            <p className="muted small">Select a hazard on the map or in the table.</p>
          )}
        </Panel>
      </div>
      <Panel title="Reported hazards">
        <QueryView
          query={hazards}
          isEmpty={(h) => h.length === 0}
          empty={<EmptyState title="No hazards reported">This does not mean the area is safe.</EmptyState>}
        >
          {(h) => (
            <DataTable
              caption="Reported hazards"
              rows={h}
              columns={cols}
              rowKey={(x) => x.id}
              onSelect={(x) => select(x.id)}
              selectedKey={selected}
            />
          )}
        </QueryView>
      </Panel>
      <Panel title="Model 2 world model (latest checkpoint)">
        <QueryView query={env}>
          {(e) => (
            <p className="small">
              {e.source} · {e.cells.length} cell(s) with reported observations · snapshot{" "}
              {formatSimTime(e.snapshot_sim_ms)} · {e.crs} ({e.units})
            </p>
          )}
        </QueryView>
      </Panel>
    </div>
  );
}
