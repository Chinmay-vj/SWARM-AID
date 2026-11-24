/**
 * Evidence center. Evidence is only ever loaded through backend-controlled references
 * (evidence-objects/{id}/content with authorization). Arbitrary URLs are never fetched and
 * artifact keys are shown as opaque identifiers. Images are rendered from an in-memory blob
 * URL only for safe raster media types; nothing else is rendered inline.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import type { Evidence, Observation } from "../../contracts/api";
import { SelectField } from "../../components/ui/data";
import { Button, Kv, PageHeader, Panel, SourceTag, StatusBadge } from "../../components/ui/primitives";
import { AlertBox, EmptyState, ErrorState, QueryView, Skeleton } from "../../components/ui/states";
import { useMissionQuery, useMode } from "../../hooks/data";
import { formatConfidence, formatLocation, formatSimTime, humanize, shortId } from "../../lib/format";

const SAFE_IMAGE_TYPES = new Set(["image/png", "image/jpeg"]);

interface Item {
  evidence: Evidence;
  observation: Observation;
}

export default function EvidencePage() {
  const { missionId } = useParams();
  const synthetic = useMode() === "synthetic";
  const [params, setParams] = useSearchParams();
  const incidentId = params.get("incident") ?? "";
  const observationId = params.get("observation") ?? "";
  const [modality, setModality] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const incidents = useMissionQuery(missionId, ["incidents", "evidence-picker"], (p, id, s) =>
    p.incidents(id, { limit: 200 }, s),
  );
  const group = useMissionQuery(
    missionId,
    ["incidents", "group", incidentId],
    (p, _id, s) => p.evidenceGroup(incidentId, s),
    { enabled: Boolean(incidentId) },
  );
  const recent = useMissionQuery(
    missionId,
    ["observations", "evidence-recent"],
    (p, id, s) => p.observations(id, { limit: 12, kind: "possible_human" }, s),
    { enabled: !incidentId && !observationId },
  );
  const single = useMissionQuery(
    missionId,
    ["observations", "detail", observationId],
    (p, _id, s) => p.observation(observationId, s),
    { enabled: Boolean(observationId) },
  );

  const observations: Observation[] = useMemo(() => {
    if (incidentId) return group.data?.observations ?? [];
    if (observationId) return single.data ? [single.data] : [];
    return recent.data?.items ?? [];
  }, [incidentId, observationId, group.data, single.data, recent.data]);

  const evidenceQuery = useMissionQuery(
    missionId,
    ["observations", "evidence-batch", observations.map((o) => o.id).join(",")],
    async (p, _id, s) => {
      const lists = await Promise.all(
        observations
          .slice(0, 30)
          .map(async (o) =>
            (await p.observationEvidence(o.id, s)).map((e) => ({ evidence: e, observation: o })),
          ),
      );
      return lists.flat();
    },
    { enabled: observations.length > 0 },
  );
  const items = (evidenceQuery.data ?? []).filter((i) => !modality || i.evidence.modality === modality);
  const modalities = [...new Set((evidenceQuery.data ?? []).map((i) => i.evidence.modality))].sort();
  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id].slice(-2)));
  const compared = selected
    .map((id) => items.find((i) => i.evidence.evidence_id === id))
    .filter((i): i is Item => Boolean(i));
  const source = incidentId ? "incident" : observationId ? "observation" : "recent";

  return (
    <div className="stack">
      <PageHeader
        title="Multimodal evidence center"
        description="Synthetic sensor evidence referenced by observations and Model 2 evidence groups. Media is shown only when a stored object exists; nothing is fetched from arbitrary locations."
        actions={<SourceTag synthetic={synthetic} />}
      />
      <Panel title="Evidence source">
        <div className="filters">
          <SelectField
            label="Incident evidence group"
            value={incidentId}
            onChange={(v) => {
              const next = new URLSearchParams();
              if (v) next.set("incident", v);
              setParams(next, { replace: true });
              setSelected([]);
            }}
            options={[
              { value: "", label: "Recent possible-human reports" },
              ...(incidents.data?.items ?? []).map((i) => ({
                value: i.id,
                label: `${humanize(i.category)} · ${shortId(i.id)} · r${i.revision} · ${humanize(i.disposition)}`,
              })),
            ]}
          />
          <SelectField
            label="Modality"
            value={modality}
            onChange={setModality}
            options={[{ value: "", label: "All" }, ...modalities.map((m) => ({ value: m, label: m }))]}
          />
          {observationId && (
            <Button size="sm" onClick={() => setParams(new URLSearchParams(), { replace: true })}>
              Clear observation filter
            </Button>
          )}
        </div>
        {incidentId && group.data && (
          <p className="small" style={{ marginTop: 8 }}>
            Evidence group <code>{shortId(group.data.evidence_group_id)}</code>:{" "}
            {group.data.observations.length} observations from {group.data.distinct_reporters.length}{" "}
            independent reporter(s): {group.data.distinct_reporters.join(", ")}.{" "}
            <Link to={`/missions/${missionId}/incidents/${incidentId}`}>Open incident</Link>
          </p>
        )}
      </Panel>
      {compared.length === 2 && (
        <Panel
          title="Side-by-side comparison"
          actions={
            <Button size="sm" onClick={() => setSelected([])}>
              Clear
            </Button>
          }
        >
          <div className="grid cols-2">
            {compared.map((i) => (
              <EvidenceDetail key={i.evidence.evidence_id} item={i} />
            ))}
          </div>
        </Panel>
      )}
      <Panel
        title={`Evidence gallery (${source})`}
        actions={<span className="xs muted">Select two items to compare</span>}
      >
        {(group.isLoading || recent.isLoading || single.isLoading || evidenceQuery.isLoading) && (
          <Skeleton rows={4} />
        )}
        {group.isError && <ErrorState error={group.error} onRetry={() => void group.refetch()} />}
        {!evidenceQuery.isLoading && observations.length === 0 && (
          <EmptyState title="No evidence to show">
            No observations are associated with this selection.
          </EmptyState>
        )}
        {evidenceQuery.isError && (
          <ErrorState error={evidenceQuery.error} onRetry={() => void evidenceQuery.refetch()} />
        )}
        {items.length > 0 && (
          <div className="card-grid">
            {items.map((i) => (
              <div
                key={i.evidence.evidence_id}
                className={`entity-card ${selected.includes(i.evidence.evidence_id) ? "selected" : ""}`}
              >
                <EvidenceMedia evidence={i.evidence} />
                <div className="row between">
                  <StatusBadge status={i.evidence.modality} tone="info" />
                  <span className="xs muted">{formatSimTime(i.evidence.captured_ms)}</span>
                </div>
                <span className="xs">
                  {i.evidence.origin} · {humanize(i.observation.kind)} · conf{" "}
                  {formatConfidence(i.observation.confidence)}
                </span>
                <label className="check xs">
                  <input
                    type="checkbox"
                    checked={selected.includes(i.evidence.evidence_id)}
                    onChange={() => toggle(i.evidence.evidence_id)}
                  />
                  Compare
                </label>
              </div>
            ))}
          </div>
        )}
        {evidenceQuery.data && items.length === 0 && observations.length > 0 && (
          <EmptyState title="No evidence for this modality" />
        )}
      </Panel>
      {selected.length === 1 && compared[0] && (
        <Panel title="Evidence detail">
          <EvidenceDetail item={compared[0]} />
        </Panel>
      )}
    </div>
  );
}

function EvidenceDetail({ item }: { item: Item }) {
  const { evidence: e, observation: o } = item;
  return (
    <div className="stack tight">
      <EvidenceMedia evidence={e} large />
      <Kv
        items={[
          ["Evidence ID", <code key="e">{e.evidence_id}</code>],
          ["Modality", e.modality],
          ["Origin agent", e.origin],
          ["Captured (sim)", formatSimTime(e.captured_ms)],
          ["Artifact reference", <code key="a">{e.artifact_key}</code>],
          ["Stored object", e.object_id ? <code key="o">{e.object_id}</code> : "none (reference only)"],
          ["Observation", <code key="ob">{shortId(o.id)}</code>],
          ["Observation category", `${humanize(o.kind)}${o.label ? ` · ${o.label}` : ""}`],
          ["Observation confidence", formatConfidence(o.confidence)],
          ["Reported location", formatLocation(o.location)],
          ["Freshness", o.stale ? "stale" : "fresh"],
        ]}
      />
      <h3>Provenance</h3>
      <ol className="small">
        <li>
          {formatSimTime(e.captured_ms)} · captured by {e.origin} ({e.modality})
        </li>
        <li>
          {formatSimTime(o.observed_ms)} · included in observation <code>{shortId(o.observation_id)}</code>
        </li>
        <li>
          {formatSimTime(o.received_ms)} · received by the coordinator · Model 2 outcome “{o.outcome}”
        </li>
      </ol>
    </div>
  );
}

/** Loads stored evidence content through the provider (authorized), never via a raw URL. */
function EvidenceMedia({ evidence, large }: { evidence: Evidence; large?: boolean }) {
  const objectId = evidence.object_id;
  return objectId ? (
    <StoredMedia objectId={objectId} large={large} />
  ) : (
    <div className="evidence-thumb" style={large ? { maxHeight: 220 } : undefined}>
      <span>
        {evidence.modality} evidence
        <br />
        No stored media for this reference (synthetic artifact key only).
      </span>
    </div>
  );
}

function StoredMedia({ objectId, large }: { objectId: string; large?: boolean }) {
  const { missionId } = useParams();
  const object = useMissionQuery(missionId, ["evidence-object", objectId], (p, _id, s) =>
    p.evidenceObject(objectId, s),
  );
  const safe = object.data && SAFE_IMAGE_TYPES.has(object.data.media_type);
  const blob = useMissionQuery(
    missionId,
    ["evidence-content", objectId],
    (p, _id, s) => p.evidenceContent(objectId, s),
    { enabled: Boolean(safe), staleTime: Infinity },
  );
  const [url, setUrl] = useState<string | null>(null);
  const [zoomed, setZoomed] = useState(false);
  useEffect(() => {
    if (!blob.data) return;
    const u = URL.createObjectURL(blob.data);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [blob.data]);
  return (
    <div className="evidence-thumb" style={large ? { maxHeight: 320 } : undefined}>
      <QueryView query={object}>
        {(o) =>
          safe ? (
            url ? (
              <button
                type="button"
                className="btn ghost"
                style={{ padding: 0, overflow: "hidden" }}
                aria-pressed={zoomed}
                aria-label={zoomed ? "Zoom out" : "Zoom in"}
                onClick={() => large && setZoomed((z) => !z)}
              >
                <img
                  src={url}
                  alt={`Synthetic evidence object ${shortId(o.id)} (${o.media_type})`}
                  style={{
                    transform: zoomed ? "scale(2)" : undefined,
                    cursor: large ? (zoomed ? "zoom-out" : "zoom-in") : undefined,
                  }}
                />
              </button>
            ) : blob.isError ? (
              <AlertBox tone="warn">Media could not be loaded.</AlertBox>
            ) : (
              <Skeleton rows={2} />
            )
          ) : (
            <span>
              {o.media_type} · {o.size_bytes} bytes · not rendered inline
            </span>
          )
        }
      </QueryView>
    </div>
  );
}
