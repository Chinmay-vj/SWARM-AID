import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { MapFeature } from "../../contracts/api";
import { LayerControls, MissionMap, useTrails, type MapSelection } from "../../components/maps/MissionMap";
import { DataTable, type Column } from "../../components/ui/data";
import { Kv, PageHeader, Panel, SourceTag, StatusBadge } from "../../components/ui/primitives";
import { QueryView } from "../../components/ui/states";
import { useLiveInterval, useMissionQuery, useMode } from "../../hooks/data";
import { formatLocation, formatSimTime, shortId } from "../../lib/format";

type Entity = MapFeature & { kind: string };

export default function MapPage() {
  const { missionId } = useParams();
  const synthetic = useMode() === "synthetic";
  const live = useLiveInterval();
  const map = useMissionQuery(missionId, ["map"], (p, id, s) => p.map(id, s), { refetchInterval: live });
  const coverage = useMissionQuery(missionId, ["coverage"], (p, id, s) => p.coverage(id, s), {
    refetchInterval: live,
  });
  const agents = useMissionQuery(missionId, ["agents"], (p, id, s) => p.agents(id, s), {
    refetchInterval: live,
  });
  const trails = useTrails(map.data);
  const [selected, setSelected] = useState<MapSelection | null>(null);
  const base = `/missions/${missionId}`;

  const entities = useMemo<Entity[]>(
    () =>
      (map.data?.layers ?? [])
        .filter((l) => ["agents", "incidents", "hazards"].includes(l.name))
        .flatMap((l) => l.features.map((f) => ({ ...f, kind: l.name }))),
    [map.data],
  );
  const selectedEntity = entities.find((e) => selected && e.kind === selected.layer && e.id === selected.id);
  const link = (e: Entity) => {
    if (e.kind === "agents") {
      const a = agents.data?.find((x) => x.agent_key === e.id);
      return a ? `${base}/fleet/${a.id}` : null;
    }
    if (e.kind === "incidents") return `${base}/incidents/${e.id}`;
    return `${base}/environment?hazard=${e.id}`;
  };
  const columns: Column<Entity>[] = [
    { key: "kind", header: "Layer", cell: (e) => e.kind, sort: (e) => e.kind },
    {
      key: "id",
      header: "Identifier",
      cell: (e) => (e.kind === "agents" ? e.id : shortId(e.id)),
      sort: (e) => e.id,
    },
    { key: "loc", header: "Reported location", cell: (e) => formatLocation(e.location) },
    {
      key: "state",
      header: "State",
      cell: (e) => (
        <span className="row" style={{ gap: 4 }}>
          {Object.entries(e.properties)
            .filter(([k]) =>
              ["communication", "availability", "disposition", "priority", "label", "category"].includes(k),
            )
            .map(([k, v]) => (
              <StatusBadge key={k} status={String(v)} />
            ))}
          {e.properties.stale === true && <StatusBadge status="stale" />}
        </span>
      ),
    },
  ];

  return (
    <div className="stack">
      <PageHeader
        title="Live simulation map"
        description="Reported positions, incidents, hazards, sectors and reported coverage on the local simulator grid. Select an entity to inspect it; the map never sends instructions to agents."
        actions={<SourceTag synthetic={synthetic} />}
      />
      <div className="grid main-side">
        <Panel title="Map">
          <QueryView query={map} rows={10}>
            {(data) => (
              <MissionMap
                data={data}
                coverage={coverage.data}
                trails={trails}
                selected={selected}
                onSelect={setSelected}
                height={560}
                synthetic={synthetic}
              />
            )}
          </QueryView>
        </Panel>
        <div className="stack">
          <Panel title="Layers">
            <LayerControls />
          </Panel>
          <Panel title="Selection">
            {selectedEntity ? (
              <div className="stack tight">
                <Kv
                  items={[
                    ["Layer", selectedEntity.kind],
                    ["Identifier", <code key="i">{selectedEntity.id}</code>],
                    ["Reported location", formatLocation(selectedEntity.location)],
                    ...Object.entries(selectedEntity.properties)
                      .filter(([k]) => k !== "cells")
                      .map(
                        ([k, v]) =>
                          [
                            k.replace(/_/g, " "),
                            k.endsWith("_ms") && typeof v === "number"
                              ? formatSimTime(v)
                              : String(v ?? "unknown"),
                          ] as [string, string],
                      ),
                  ]}
                />
                {link(selectedEntity) && <Link to={link(selectedEntity)!}>Open details</Link>}
              </div>
            ) : (
              <p className="muted small">
                Select an agent, incident or hazard on the map or in the list below.
              </p>
            )}
          </Panel>
        </div>
      </div>
      <Panel title="Entity list (accessible alternative to the map)">
        <DataTable
          caption="Map entities"
          rows={entities}
          columns={columns}
          rowKey={(e) => `${e.kind}:${e.id}`}
          onSelect={(e) => setSelected({ layer: e.kind as MapSelection["layer"], id: e.id })}
          selectedKey={selected ? `${selected.layer}:${selected.id}` : null}
        />
      </Panel>
    </div>
  );
}
