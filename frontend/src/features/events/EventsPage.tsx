import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import type { MissionEvent } from "../../contracts/api";
import { ALL_TOPICS, eventTopic } from "../../contracts/events";
import { SearchField, SelectField } from "../../components/ui/data";
import { Button, PageHeader, Panel, SourceTag } from "../../components/ui/primitives";
import { AlertBox } from "../../components/ui/states";
import { useMode, useProvider } from "../../hooks/data";
import { asApiError } from "../../services/api/errors";
import { TIMELINE_CAPACITY, useActivity } from "../../stores/activity";
import { EventList } from "./EventList";

export default function EventsPage() {
  const { missionId } = useParams();
  const synthetic = useMode() === "synthetic";
  const provider = useProvider();
  const live = useActivity((s) => s.events);
  const [history, setHistory] = useState<MissionEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [topic, setTopic] = useState("");
  const [source, setSource] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const merged = useMemo(() => {
    const bySeq = new Map<number, MissionEvent>();
    [...history, ...live].forEach((e) => bySeq.set(e.sequence, e));
    return [...bySeq.values()].sort((a, b) => b.sequence - a.sequence);
  }, [history, live]);
  const sources = useMemo(() => [...new Set(merged.map((e) => e.source))].sort(), [merged]);
  const filtered = merged.filter((e) => {
    if (topic && eventTopic(e.event_type) !== topic) return false;
    if (source && e.source !== source) return false;
    const t = e.sim_time_ms;
    if (from && (t === null || t < Number(from) * 1000)) return false;
    if (to && (t === null || t > Number(to) * 1000)) return false;
    return true;
  });

  const loadHistory = async () => {
    if (!missionId) return;
    setLoading(true);
    setError(null);
    try {
      const out: MissionEvent[] = [];
      let after = 0;
      for (let i = 0; i < 5; i++) {
        const batch = await provider.events(missionId, { after, limit: 1000 });
        out.push(...batch);
        if (batch.length < 1000) break;
        after = batch[batch.length - 1]!.sequence;
      }
      setHistory(out.slice(-2000));
    } catch (e) {
      setError(asApiError(e).userMessage);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="stack">
      <PageHeader
        title="Event timeline"
        description={`Ordered mission events (de-duplicated by sequence). Live history is bounded to ${TIMELINE_CAPACITY} events; load the persisted log for older events.`}
        actions={<SourceTag synthetic={synthetic} />}
      />
      <Panel
        title="Filters"
        actions={
          <Button onClick={() => void loadHistory()} disabled={loading}>
            {loading ? "Loading…" : "Load persisted history (up to 2000)"}
          </Button>
        }
      >
        <div className="filters">
          <SelectField label="Category" value={topic} onChange={setTopic} options={["", ...ALL_TOPICS]} />
          <SelectField label="Source" value={source} onChange={setSource} options={["", ...sources]} />
          <SearchField
            label="From (sim s)"
            value={from}
            onChange={(v) => setFrom(v.replace(/[^0-9.]/g, ""))}
          />
          <SearchField label="To (sim s)" value={to} onChange={(v) => setTo(v.replace(/[^0-9.]/g, ""))} />
        </div>
        {error && <AlertBox tone="bad">{error}</AlertBox>}
      </Panel>
      <Panel title={`Events (${filtered.length} shown of ${merged.length} loaded)`}>
        <EventList
          events={filtered}
          missionId={missionId!}
          maxHeight={640}
          limit={500}
          synthetic={synthetic}
        />
      </Panel>
    </div>
  );
}
