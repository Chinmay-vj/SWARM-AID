import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { OBSERVATION_KINDS, type Observation } from "../../contracts/api";
import { DataTable, Pagination, SearchField, SelectField, type Column } from "../../components/ui/data";
import { Kv, PageHeader, Panel, SourceTag, StatusBadge } from "../../components/ui/primitives";
import { EmptyState, QueryView } from "../../components/ui/states";
import { useLiveInterval, useMissionQuery, useMode } from "../../hooks/data";
import {
  formatConfidence,
  formatDuration,
  formatLocation,
  formatSimTime,
  humanize,
  shortId,
} from "../../lib/format";

const PAGE = 50;

export default function ObservationsPage() {
  const { missionId } = useParams();
  const synthetic = useMode() === "synthetic";
  const live = useLiveInterval();
  const [params, setParams] = useSearchParams();
  const kind = params.get("kind") ?? "";
  const reporter = params.get("reporter") ?? "";
  const outcome = params.get("outcome") ?? "";
  const sort = (params.get("sort") as "observed_ms" | "-observed_ms" | null) ?? "-observed_ms";
  const since = params.get("since") ?? "";
  const offset = Number(params.get("offset") ?? 0);
  const [selected, setSelected] = useState<string | null>(params.get("focus"));
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    if (k !== "offset") next.delete("offset");
    setParams(next, { replace: true });
  };
  const q = {
    kind: kind || undefined,
    reporter: reporter || undefined,
    outcome: outcome || undefined,
    sort,
    since_ms: since ? Number(since) * 1000 : undefined,
    limit: PAGE,
    offset,
  };
  const list = useMissionQuery(missionId, ["observations", q], (p, id, s) => p.observations(id, q, s), {
    refetchInterval: live,
  });
  const agents = useMissionQuery(missionId, ["agents"], (p, id, s) => p.agents(id, s));
  const detail = useMissionQuery(
    missionId,
    ["observations", "detail", selected],
    (p, _id, s) => p.observation(selected!, s),
    { enabled: Boolean(selected) },
  );
  const evidence = useMissionQuery(
    missionId,
    ["observations", "evidence", selected],
    (p, _id, s) => p.observationEvidence(selected!, s),
    { enabled: Boolean(selected) },
  );

  const columns = useMemo<Column<Observation>[]>(
    () => [
      {
        key: "obs",
        header: "Observed (sim)",
        cell: (o) => <span className="mono">{formatSimTime(o.observed_ms)}</span>,
      },
      {
        key: "recv",
        header: "Received (sim)",
        cell: (o) => <span className="mono">{formatSimTime(o.received_ms)}</span>,
      },
      { key: "rep", header: "Source agent", cell: (o) => o.reporter },
      {
        key: "kind",
        header: "Category",
        cell: (o) => (
          <StatusBadge
            status={o.kind}
            tone={o.kind === "possible_human" ? "warn" : o.kind === "hazard" ? "info" : "muted"}
          />
        ),
      },
      { key: "label", header: "Label", cell: (o) => o.label ?? <span className="muted">—</span> },
      {
        key: "conf",
        header: "Confidence",
        cell: (o) => formatConfidence(o.confidence),
        sort: (o) => o.confidence,
      },
      { key: "loc", header: "Reported location", cell: (o) => formatLocation(o.location) },
      {
        key: "out",
        header: "Model 2 outcome",
        cell: (o) => <StatusBadge status={o.outcome} tone={o.outcome === "admitted" ? "ok" : "muted"} />,
      },
      {
        key: "fresh",
        header: "Freshness",
        cell: (o) => (
          <StatusBadge
            status={o.stale ? "stale" : "fresh"}
            label={`${o.stale ? "stale" : "fresh"} · ${formatDuration(o.age_ms)}`}
          />
        ),
      },
    ],
    [],
  );

  return (
    <div className="stack">
      <PageHeader
        title="Observation center"
        description="Every report received from Model 1 agents, with provenance. Routine environmental reports are kept separate from possible rescue-related reports; observations are not incidents."
        actions={<SourceTag synthetic={synthetic} />}
      />
      <Panel title="Filters">
        <div className="filters">
          <SelectField
            label="Category"
            value={kind}
            onChange={(v) => set("kind", v)}
            options={[
              { value: "", label: "All" },
              ...OBSERVATION_KINDS.map((k) => ({ value: k, label: humanize(k) })),
            ]}
          />
          <SelectField
            label="Source agent"
            value={reporter}
            onChange={(v) => set("reporter", v)}
            options={[
              { value: "", label: "All" },
              ...(agents.data ?? []).map((a) => ({ value: a.agent_key, label: a.agent_key })),
            ]}
          />
          <SelectField
            label="Outcome"
            value={outcome}
            onChange={(v) => set("outcome", v)}
            options={["", "admitted", "duplicate", "stale", "not_processed", "queued"]}
          />
          <SearchField
            label="Since (sim seconds)"
            value={since}
            onChange={(v) => set("since", v.replace(/[^0-9.]/g, ""))}
            placeholder="0"
          />
          <SelectField
            label="Order"
            value={sort}
            onChange={(v) => set("sort", v)}
            options={[
              { value: "-observed_ms", label: "Newest first" },
              { value: "observed_ms", label: "Oldest first" },
            ]}
          />
        </div>
      </Panel>
      <div className="grid main-side">
        <Panel title="Observations">
          <QueryView
            query={list}
            rows={8}
            isEmpty={(p) => p.items.length === 0}
            empty={
              <EmptyState title="No observations match">Observations appear once agents report.</EmptyState>
            }
          >
            {(p) => (
              <>
                <DataTable
                  caption="Observations"
                  rows={p.items}
                  columns={columns}
                  rowKey={(o) => o.id}
                  onSelect={(o) => setSelected(o.id)}
                  selectedKey={selected}
                />
                <Pagination
                  total={p.total}
                  limit={PAGE}
                  offset={offset}
                  onChange={(o) => set("offset", String(o))}
                />
              </>
            )}
          </QueryView>
        </Panel>
        <Panel title="Observation detail">
          {!selected ? (
            <p className="muted small">Select an observation to see provenance and evidence.</p>
          ) : (
            <QueryView query={detail}>
              {(o) => (
                <div className="stack tight">
                  <Kv
                    items={[
                      ["Database ID", <code key="a">{o.id}</code>],
                      ["Observation ID (stable)", <code key="b">{o.observation_id}</code>],
                      ["Message ID", <code key="c">{o.message_id}</code>],
                      ["Source agent", o.reporter],
                      ["Source channel", o.source],
                      ["Category / label", `${humanize(o.kind)}${o.label ? ` · ${o.label}` : ""}`],
                      ["Confidence", formatConfidence(o.confidence)],
                      [
                        "Observed / received",
                        `${formatSimTime(o.observed_ms)} / ${formatSimTime(o.received_ms)}`,
                      ],
                      ["Age", `${formatDuration(o.age_ms)} (${o.stale ? "stale" : "fresh"})`],
                      ["Reported location", formatLocation(o.location)],
                      ["Model 2 outcome", <StatusBadge key="o" status={o.outcome} tone="info" />],
                    ]}
                  />
                  <h3>Evidence references</h3>
                  <QueryView
                    query={evidence}
                    isEmpty={(e) => e.length === 0}
                    empty={<p className="muted small">No evidence references.</p>}
                  >
                    {(list) => (
                      <ul className="small">
                        {list.map((e) => (
                          <li key={e.evidence_id}>
                            {e.modality} · {e.origin} · {formatSimTime(e.captured_ms)} ·{" "}
                            <code>{shortId(e.evidence_id)}</code>
                            {e.object_id ? " · stored object" : " · reference only"}
                          </li>
                        ))}
                      </ul>
                    )}
                  </QueryView>
                  <Link to={`/missions/${missionId}/evidence?observation=${o.id}`}>
                    Open in evidence center
                  </Link>
                </div>
              )}
            </QueryView>
          )}
        </Panel>
      </div>
    </div>
  );
}
