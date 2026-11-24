/**
 * Mission map in local simulator grid coordinates (crs "swarm-aid:grid", unit: cell).
 * Only reported information is drawn: agent health-report positions, Model 2 incidents,
 * reported hazards, sectors from public configuration and agent-reported coverage. Clicking
 * the map never issues instructions to agents.
 */
import { Crosshair, Minus, Plus, RotateCcw } from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
  type WheelEvent,
} from "react";
import type { Coverage, MapFeature, MissionMap as MapData } from "../../contracts/api";
import { drawable, fitView, toScreen, zoomAt, type View } from "../../lib/grid";
import { formatSimTime } from "../../lib/format";
import { usePreferences, type MapLayer } from "../../stores/preferences";
import { Button } from "../ui/primitives";

export interface MapSelection {
  layer: "agents" | "incidents" | "hazards" | "stale_observations";
  id: string;
}

export type Trails = Record<string, [number, number][]>;

const PRIORITY_COLOR: Record<string, string> = {
  potentially_urgent: "var(--bad)",
  elevated: "var(--warn)",
  review_required: "var(--info)",
};

function layer(data: MapData, name: string): MapFeature[] {
  return data.layers.find((l) => l.name === name)?.features ?? [];
}

/** Accumulates reported positions across map refreshes (dashboard-observed movement history). */
export function useTrails(data: MapData | undefined, max = 16): Trails {
  const store = useRef<{ ref: string; trails: Trails }>({ ref: "", trails: {} });
  return useMemo(() => {
    if (!data) return {};
    if (store.current.ref !== data.map_ref) store.current = { ref: data.map_ref, trails: {} };
    const trails = { ...store.current.trails };
    for (const f of layer(data, "agents")) {
      if (!drawable(f.location, data.width, data.height)) continue;
      const point: [number, number] = [f.location.x, f.location.y];
      const prev = trails[f.id] ?? [];
      const last = prev[prev.length - 1];
      trails[f.id] =
        last && last[0] === point[0] && last[1] === point[1] ? prev : [...prev, point].slice(-max);
    }
    store.current.trails = trails;
    return trails;
  }, [data, max]);
}

export function MissionMap({
  data,
  coverage,
  trails,
  selected,
  onSelect,
  height = 460,
  synthetic,
}: {
  data: MapData;
  coverage?: Coverage;
  trails?: Trails;
  selected?: MapSelection | null;
  onSelect?: (s: MapSelection) => void;
  height?: number;
  synthetic?: boolean;
}) {
  const layers = usePreferences((s) => s.mapLayers);
  const smoothing = usePreferences((s) => s.mapSmoothing && !s.reducedMotion);
  const wrap = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: height });
  const [view, setView] = useState<View>(() => fitView(data.width, data.height, 800, height));
  const [userMoved, setUserMoved] = useState(false);
  const drag = useRef<{ x: number; y: number; view: View } | null>(null);
  const on = (l: MapLayer) => layers[l];

  useEffect(() => {
    const el = wrap.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => {
      if (entry) setSize({ w: Math.max(200, entry.contentRect.width), h: height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [height]);

  const fit = useCallback(() => {
    setView(fitView(data.width, data.height, size.w, size.h));
    setUserMoved(false);
  }, [data.width, data.height, size.w, size.h]);
  useEffect(() => {
    if (!userMoved) setView(fitView(data.width, data.height, size.w, size.h));
  }, [data.width, data.height, size.w, size.h, userMoved]);

  const zoom = (factor: number, ax = size.w / 2, ay = size.h / 2) => {
    setView((v) => zoomAt(v, factor, ax, ay));
    setUserMoved(true);
  };
  const onWheel = (e: WheelEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    zoom(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - rect.left, e.clientY - rect.top);
  };
  const onPointerDown = (e: PointerEvent<SVGSVGElement>) => {
    if ((e.target as Element).closest("[data-entity]")) return;
    drag.current = { x: e.clientX, y: e.clientY, view };
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };
  const onPointerMove = (e: PointerEvent<SVGSVGElement>) => {
    const d = drag.current;
    if (!d) return;
    setView({ ...d.view, tx: d.view.tx + e.clientX - d.x, ty: d.view.ty + e.clientY - d.y });
    setUserMoved(true);
  };
  const onPointerUp = () => (drag.current = null);
  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    const step = 40;
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [step, 0],
      ArrowRight: [-step, 0],
      ArrowUp: [0, step],
      ArrowDown: [0, -step],
    };
    if (moves[e.key] && e.target === e.currentTarget) {
      e.preventDefault();
      const [dx, dy] = moves[e.key]!;
      setView((v) => ({ ...v, tx: v.tx + dx, ty: v.ty + dy }));
      setUserMoved(true);
    } else if (e.key === "+" || e.key === "=") zoom(1.2);
    else if (e.key === "-") zoom(1 / 1.2);
    else if (e.key === "0") fit();
  };

  const s = view.scale;
  const cellRect = (x: number, y: number) => ({
    x: x * s + view.tx,
    y: y * s + view.ty,
    width: s,
    height: s,
  });
  const select = (sel: MapSelection) => onSelect?.(sel);
  const entityKey = (e: KeyboardEvent, sel: MapSelection) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      select(sel);
    }
  };
  const isSel = (l: string, id: string) => selected?.layer === l && selected.id === id;

  const reported = new Map<string, { stale: boolean }>();
  coverage?.reported_cells.forEach((c) => reported.set(`${c.cell[0]},${c.cell[1]}`, { stale: c.stale }));
  const agents = layer(data, "agents");
  const incidents = layer(data, "incidents");
  const hazards = layer(data, "hazards");
  const sightings = layer(data, "stale_observations");
  const sectors = layer(data, "sectors");
  const undrawable = [...agents, ...incidents, ...hazards].filter(
    (f) => !drawable(f.location, data.width, data.height),
  ).length;

  const cells = [];
  for (let x = 0; x < data.width; x++)
    for (let y = 0; y < data.height; y++) {
      const r = reported.get(`${x},${y}`);
      const fill =
        r && on("coverage")
          ? r.stale
            ? "var(--map-coverage-stale)"
            : "var(--map-coverage)"
          : !r && on("unknown")
            ? "var(--map-unknown)"
            : "var(--map-cell)";
      cells.push(
        <rect
          key={`c${x},${y}`}
          {...cellRect(x, y)}
          fill={fill}
          stroke={on("grid") ? "var(--map-grid)" : "none"}
          strokeWidth={0.6}
          strokeDasharray={!r && on("unknown") ? "3 3" : undefined}
        />,
      );
    }

  return (
    <div className="stack tight">
      <div className="map-wrap" ref={wrap} style={{ height }}>
        <svg
          className="map-svg"
          width="100%"
          height={height}
          role="application"
          aria-roledescription="interactive map"
          aria-label={`Mission map, local grid ${data.width} by ${data.height} cells. Arrow keys pan, plus and minus zoom, 0 fits. Use the entity list for a non-visual alternative.`}
          tabIndex={0}
          onWheel={onWheel}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={onPointerUp}
          onKeyDown={onKey}
        >
          <g>{cells}</g>
          {on("sectors") &&
            sectors.map((f) => {
              const pts = (f.properties.cells as [number, number][] | undefined) ?? [];
              if (!pts.length) return null;
              const xs = pts.map((p) => p[0]);
              const ys = pts.map((p) => p[1]);
              const x0 = Math.min(...xs);
              const y0 = Math.min(...ys);
              const r = {
                x: x0 * s + view.tx,
                y: y0 * s + view.ty,
                width: (Math.max(...xs) - x0 + 1) * s,
                height: (Math.max(...ys) - y0 + 1) * s,
              };
              return (
                <g key={`s-${f.id}`} pointerEvents="none">
                  <rect
                    {...r}
                    fill="none"
                    stroke="var(--map-sector)"
                    strokeWidth={1.4}
                    strokeDasharray="6 4"
                  />
                  {on("labels") && (
                    <text x={r.x + 4} y={r.y + 12} fontSize={10} fill="var(--muted)">
                      sector {f.id}
                    </text>
                  )}
                </g>
              );
            })}
          {on("hazards") &&
            hazards.map((f) => {
              if (!drawable(f.location, data.width, data.height)) return null;
              const r = cellRect(f.location.x, f.location.y);
              const stale = Boolean(f.properties.stale);
              const sel: MapSelection = { layer: "hazards", id: f.id };
              return (
                <g
                  key={`h-${f.id}`}
                  data-entity
                  role="button"
                  tabIndex={0}
                  aria-label={`Hazard ${String(f.properties.label)} at cell ${f.location.x},${f.location.y}${stale ? ", stale" : ""}`}
                  onClick={() => select(sel)}
                  onKeyDown={(e) => entityKey(e, sel)}
                  style={{ cursor: "pointer" }}
                >
                  <rect
                    x={r.x + 3}
                    y={r.y + 3}
                    width={r.width - 6}
                    height={r.height - 6}
                    rx={3}
                    fill="var(--map-hazard)"
                    fillOpacity={stale ? 0.25 : 0.55}
                    stroke={isSel("hazards", f.id) ? "var(--focus)" : "var(--map-hazard)"}
                    strokeWidth={isSel("hazards", f.id) ? 2.5 : 1}
                    strokeDasharray={stale ? "3 2" : undefined}
                  />
                  {on("labels") && s > 26 && (
                    <text
                      x={r.x + r.width / 2}
                      y={r.y + r.height / 2 + 3}
                      textAnchor="middle"
                      fontSize={9}
                      fill="var(--text-strong)"
                    >
                      {String(f.properties.label).slice(0, 10)}
                    </text>
                  )}
                </g>
              );
            })}
          {on("sightings") &&
            sightings.map((f) => {
              if (!drawable(f.location, data.width, data.height)) return null;
              const [cx, cy] = toScreen(view, f.location.x, f.location.y);
              return (
                <circle
                  key={`o-${f.id}`}
                  cx={cx}
                  cy={cy}
                  r={s * 0.38}
                  fill="none"
                  stroke="var(--map-sighting)"
                  strokeOpacity={0.5}
                  strokeDasharray="4 3"
                  pointerEvents="none"
                />
              );
            })}
          {on("trails") &&
            trails &&
            Object.entries(trails).map(([id, pts]) =>
              pts.length > 1 ? (
                <polyline
                  key={`t-${id}`}
                  points={pts.map(([x, y]) => toScreen(view, x, y).join(",")).join(" ")}
                  fill="none"
                  stroke="var(--map-agent)"
                  strokeOpacity={0.35}
                  strokeWidth={2}
                  pointerEvents="none"
                />
              ) : null,
            )}
          {on("incidents") &&
            incidents.map((f) => {
              if (!drawable(f.location, data.width, data.height)) return null;
              const [cx, cy] = toScreen(view, f.location.x, f.location.y);
              const color = PRIORITY_COLOR[String(f.properties.priority)] ?? "var(--map-incident)";
              const closed = ["closed", "rejected", "expired"].includes(String(f.properties.disposition));
              const sel: MapSelection = { layer: "incidents", id: f.id };
              const d = Math.max(6, s * 0.22);
              return (
                <g
                  key={`i-${f.id}`}
                  data-entity
                  role="button"
                  tabIndex={0}
                  aria-label={`Incident ${String(f.properties.category)} ${String(f.properties.disposition)} priority ${String(f.properties.priority ?? "unknown")} at cell ${f.location.x},${f.location.y}`}
                  onClick={() => select(sel)}
                  onKeyDown={(e) => entityKey(e, sel)}
                  style={{ cursor: "pointer" }}
                  opacity={closed ? 0.45 : 1}
                >
                  {on("uncertainty") && f.location.uncertainty ? (
                    <circle
                      cx={cx}
                      cy={cy}
                      r={f.location.uncertainty * s * 1.42}
                      fill={color}
                      fillOpacity={0.08}
                      stroke={color}
                      strokeOpacity={0.4}
                      strokeDasharray="2 3"
                    />
                  ) : null}
                  <rect
                    x={cx - d}
                    y={cy - d}
                    width={d * 2}
                    height={d * 2}
                    transform={`rotate(45 ${cx} ${cy})`}
                    fill={color}
                    stroke={isSel("incidents", f.id) ? "var(--focus)" : "var(--bg)"}
                    strokeWidth={isSel("incidents", f.id) ? 3 : 1}
                  />
                </g>
              );
            })}
          {on("agents") &&
            agents.map((f) => {
              if (!drawable(f.location, data.width, data.height)) return null;
              const [cx, cy] = toScreen(view, f.location.x, f.location.y);
              const stale = Boolean(f.properties.stale);
              const disconnected = f.properties.communication === "disconnected";
              const unavailable = f.properties.availability === "unavailable";
              const color = unavailable
                ? "var(--unknown)"
                : disconnected
                  ? "var(--bad)"
                  : stale
                    ? "var(--warn)"
                    : "var(--map-agent)";
              const r = Math.max(7, s * 0.3);
              const sel: MapSelection = { layer: "agents", id: f.id };
              const label = `Agent ${f.id} at cell ${f.location.x},${f.location.y}, ${String(f.properties.communication)}, ${String(f.properties.availability)}${stale ? ", position stale" : ""}`;
              return (
                <g
                  key={`a-${f.id}`}
                  data-entity
                  role="button"
                  tabIndex={0}
                  aria-label={label}
                  onClick={() => select(sel)}
                  onKeyDown={(e) => entityKey(e, sel)}
                  style={{
                    cursor: "pointer",
                    transform: `translate(${cx}px, ${cy}px)`,
                    transition: smoothing && !stale && !drag.current ? "transform 0.35s linear" : undefined,
                  }}
                >
                  {on("uncertainty") && f.location.uncertainty ? (
                    <circle
                      r={f.location.uncertainty * s * 1.42}
                      fill="none"
                      stroke={color}
                      strokeOpacity={0.35}
                      strokeDasharray="2 3"
                    />
                  ) : null}
                  <circle
                    r={r}
                    fill="var(--surface)"
                    stroke={isSel("agents", f.id) ? "var(--focus)" : color}
                    strokeWidth={isSel("agents", f.id) ? 3 : 2}
                    strokeDasharray={stale || disconnected ? "3 2" : undefined}
                  />
                  <path
                    d={`M${-r * 0.5},0 L${r * 0.5},0 M0,${-r * 0.5} L0,${r * 0.5}`}
                    stroke={color}
                    strokeWidth={1.6}
                  />
                  {on("labels") && (
                    <text
                      y={r + 11}
                      textAnchor="middle"
                      fontSize={10}
                      fontWeight={700}
                      fill="var(--text-strong)"
                    >
                      {f.id}
                      {stale ? " (stale)" : ""}
                    </text>
                  )}
                </g>
              );
            })}
        </svg>
        <div className="map-tools">
          <Button
            size="sm"
            aria-label="Zoom in"
            icon={<Plus size={14} aria-hidden="true" />}
            onClick={() => zoom(1.25)}
          />
          <Button
            size="sm"
            aria-label="Zoom out"
            icon={<Minus size={14} aria-hidden="true" />}
            onClick={() => zoom(1 / 1.25)}
          />
          <Button
            size="sm"
            aria-label="Fit to view"
            icon={<Crosshair size={14} aria-hidden="true" />}
            onClick={fit}
          />
          <Button
            size="sm"
            aria-label="Reset view"
            icon={<RotateCcw size={14} aria-hidden="true" />}
            onClick={fit}
          />
        </div>
      </div>
      <MapLegend data={data} undrawable={undrawable} smoothing={smoothing} synthetic={synthetic} />
    </div>
  );
}

export function MapLegend({
  data,
  undrawable,
  smoothing,
  synthetic,
}: {
  data: MapData;
  undrawable: number;
  smoothing: boolean;
  synthetic?: boolean;
}) {
  return (
    <div className="stack tight">
      <div className="legend" aria-label="Map legend">
        <span>
          <i className="swatch" style={{ background: "var(--map-coverage)" }} />
          Reported coverage
        </span>
        <span>
          <i className="swatch" style={{ background: "var(--map-coverage-stale)" }} />
          Coverage (stale)
        </span>
        <span>
          <i className="swatch" style={{ background: "var(--map-unknown)", borderStyle: "dashed" }} />
          Unknown / not reported
        </span>
        <span>
          <i className="swatch" style={{ background: "var(--map-hazard)" }} />
          Reported hazard
        </span>
        <span>
          <i className="swatch" style={{ borderColor: "var(--map-sector)", borderStyle: "dashed" }} />
          Search sector
        </span>
        <span>
          <i className="swatch" style={{ background: "var(--map-agent)", borderRadius: "50%" }} />
          Agent (dashed = stale/disconnected)
        </span>
        <span>
          <i className="swatch" style={{ background: "var(--bad)", transform: "rotate(45deg)" }} />
          Incident ◆ by priority
        </span>
        <span>
          <i
            className="swatch"
            style={{ borderColor: "var(--map-sighting)", borderStyle: "dashed", borderRadius: "50%" }}
          />
          Older sighting
        </span>
      </div>
      <p className="xs muted">
        {synthetic ? "SYNTHETIC · " : ""}
        {data.crs} · units: {data.units} · {data.width}×{data.height} · reference {data.map_ref} ·{" "}
        {formatSimTime(data.sim_time_ms)}. Local simulator cells, not GPS. Positions are the last agent
        reports; reported coverage is not verified coverage.
        {smoothing ? " Marker movement is interpolated for display only." : ""}
        {undrawable > 0
          ? ` ${undrawable} item(s) without a valid reported location are listed but not drawn.`
          : ""}
      </p>
    </div>
  );
}

export function LayerControls() {
  const { mapLayers, toggleLayer, mapSmoothing, update } = usePreferences();
  return (
    <fieldset className="stack tight" style={{ border: 0, padding: 0, margin: 0 }}>
      <legend className="xs muted">Map layers</legend>
      <div className="layer-list">
        {(Object.keys(mapLayers) as MapLayer[]).map((l) => (
          <label key={l} className="check">
            <input type="checkbox" checked={mapLayers[l]} onChange={() => toggleLayer(l)} />
            {l}
          </label>
        ))}
        <label className="check">
          <input
            type="checkbox"
            checked={mapSmoothing}
            onChange={() => update({ mapSmoothing: !mapSmoothing })}
          />
          smooth movement
        </label>
      </div>
    </fieldset>
  );
}
