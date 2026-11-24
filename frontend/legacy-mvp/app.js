// SWARM-AID Phase 8 dashboard — Synthetic Demo Mode (deterministic local playback).
// All data in this mode is SYNTHETIC and labeled as such. No physical drone control.
"use strict";
const W = 12, H = 10, C = 50, HORIZON = 140, OUTAGE = [52, 62];
const $ = (id) => document.getElementById(id);
const SCEN = {
  flood_basic: { label: "Flood", hazard: "water", color: "#1d4ed8" },
  wildfire_basic: { label: "Wildfire", hazard: "fire", color: "#dc2626" },
  earthquake_basic: { label: "Earthquake", hazard: "debris", color: "#92400e" },
  cyclone_basic: { label: "Cyclone", hazard: "water", color: "#0369a1" },
  landslide_basic: { label: "Landslide", hazard: "debris", color: "#78350f" },
};
const key = (x, y) => `${x},${y}`;
function rng(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32); }

let S, timer = null;

function reset() {
  if (timer) { clearInterval(timer); timer = null; }
  const scen = $("selScenario").value, n = +$("selDrones").value, r = rng(42);
  const terrain = new Map();
  [[2, 1], [3, 1], [2, 2], [6, 6], [7, 6], [6, 7], [10, 1], [10, 2], [4, 5]].forEach(([x, y]) => terrain.set(key(x, y), "building"));
  const hz = SCEN[scen].hazard;
  [[7, 2], [8, 3], [8, 4], [9, 4], [9, 5], [3, 7], [4, 7], [3, 8], [10, 8]].forEach(([x, y]) => terrain.set(key(x, y), hz));
  terrain.set(key(0, 4), "base");
  const people = [[8, 2], [9, 7], [5, 8]]; // hidden synthetic truth: never drawn directly
  const drones = [];
  for (let i = 0; i < n; i++) {
    const x0 = Math.floor((i * W) / n), x1 = Math.floor(((i + 1) * W) / n) - 1;
    const path = [];
    for (let x = x0; x <= x1; x++) for (let k = 0; k < H; k++) path.push([x, x % 2 ? H - 1 - k : k]);
    drones.push({ key: `d${i}`, label: `Drone ${String(i + 1).padStart(2, "0")}`, x: 0, y: 4, trail: [], path, wp: 0,
      sector: `cols ${x0}-${x1}`, comm: "connected", avail: "available", activity: "launching", obs: 0,
      battery: 100, sensors: ["thermal", "rgb", "gps", "imu"], lastMs: 0, history: [], recent: [] });
  }
  S = { scen, tick: 0, status: "Ready", terrain, people, drones, coverage: new Map(), sightings: [], incidents: [], recs: [],
    events: [], series: [], queue: [], pulses: [], comm: { sent: 0, delivered: 0, peer: 0, queued: 0, down: false, recoveries: 0 },
    model2: { state: "available", reports: 0, fused: 0, last: "Awaiting drone reports" }, r, selDrone: null, selInc: null, seen: new Set() };
  $("tScenario").textContent = SCEN[scen].label;
  log("System", "mission", `Synthetic ${SCEN[scen].label} mission prepared with ${n} Model 1 drone agents`, "ready");
  render();
}

function log(src, cat, text, status = "info") { S.events.unshift({ ms: S.tick * 100, src, cat, text, status }); S.events.length = Math.min(S.events.length, 200); }
function pulse(from, to, color = "#22d3ee") { S.pulses.push({ from, to, t: 0, color }); }

function step() {
  if (S.tick >= HORIZON) { finish(); return; }
  S.tick++;
  const t = S.tick, r = S.r;
  const down = t >= OUTAGE[0] && t < OUTAGE[1];
  if (down && !S.comm.down) { S.comm.down = true; S.model2.state = "link degraded"; log("Network", "communication", "Command link interrupted — drones continue autonomously and queue reports", "warn"); }
  if (!down && S.comm.down) { S.comm.down = false; S.comm.recoveries++; S.model2.state = "available"; log("Network", "communication", `Command link restored — delivering ${S.queue.length} queued reports`, "ok"); }
  for (const d of S.drones) {
    if (d.battery <= 5) { d.activity = "returning (low battery)"; continue; }
    const [tx, ty] = d.path[d.wp % d.path.length];
    if (d.x === tx && d.y === ty) d.wp++;
    const [nx, ny] = d.path[d.wp % d.path.length];
    d.x += Math.sign(nx - d.x); if (d.x === nx) d.y += Math.sign(ny - d.y);
    d.trail.push([d.x, d.y]); if (d.trail.length > 14) d.trail.shift();
    d.battery = Math.max(0, d.battery - 0.55); d.activity = "searching sector"; d.comm = down ? "disconnected" : "connected";
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
      const cx = d.x + dx, cy = d.y + dy; if (cx >= 0 && cy >= 0 && cx < W && cy < H) S.coverage.set(key(cx, cy), t);
    }
    // Model 1 local perception (synthetic sensor model)
    if (t % 4 === 0) report(d, "environment", d.x, d.y, S.terrain.get(key(d.x, d.y)) || "clear");
    const h = S.terrain.get(key(d.x, d.y));
    if (h && h !== "building" && h !== "base" && !S.seen.has(d.key + key(d.x, d.y))) { S.seen.add(d.key + key(d.x, d.y)); report(d, "hazard", d.x, d.y, h); }
    for (const [px, py] of S.people) {
      if (Math.abs(px - d.x) <= 1 && Math.abs(py - d.y) <= 1 && r() < 0.35) report(d, "possible_human", px, py, null);
    }
    if (r() < 0.25 && S.drones.length > 1) { const o = S.drones[(S.drones.indexOf(d) + 1) % S.drones.length]; S.comm.peer++; pulse(d.key, o.key, "#a78bfa"); }
  }
  if (!down) { const q = S.queue.splice(0); q.forEach(model2Receive); }
  S.series.push({ t, cov: S.coverage.size / (W * H), obs: S.drones.reduce((a, d) => a + d.obs, 0),
    avail: S.drones.filter((d) => d.battery > 5).length, msgs: S.comm.sent, inc: S.incidents.length });
  S.pulses.forEach((p) => (p.t += 0.25)); S.pulses = S.pulses.filter((p) => p.t < 1);
  render();
}

function report(d, kind, x, y, label) {
  d.obs++; d.lastMs = S.tick * 100; S.comm.sent++;
  const rep = { id: `obs-${S.comm.sent}`, drone: d.key, label: d.label, kind, x, y, tag: label, ms: S.tick * 100, conf: +(0.45 + S.r() * 0.4).toFixed(2) };
  d.recent.unshift(rep); d.recent.length = Math.min(d.recent.length, 8);
  if (kind === "possible_human") {
    S.sightings.push(rep);
    log(d.label, "Model 1", `reports possible human sighting at cell (${x},${y}) — confidence ${rep.conf}`, "warn");
  } else if (kind === "hazard") log(d.label, "Model 1", `reports ${label} hazard at (${x},${y})`, "info");
  if (S.comm.down) { S.queue.push(rep); S.comm.queued++; d.comm = "disconnected"; return; }
  model2Receive(rep);
}

function model2Receive(rep) {
  S.comm.delivered++; S.model2.reports++; pulse(rep.drone, "m2");
  if (rep.kind !== "possible_human") return;
  let inc = S.incidents.find((i) => i.x === rep.x && i.y === rep.y);
  const hazardNear = [...S.terrain].some(([k, v]) => { const [hx, hy] = k.split(",").map(Number); return v !== "building" && v !== "base" && Math.abs(hx - rep.x) + Math.abs(hy - rep.y) <= 2; });
  if (!inc) {
    inc = { id: `INC-${String(S.incidents.length + 1).padStart(3, "0")}`, x: rep.x, y: rep.y, sources: new Set(), evidence: [], conflict: 0,
      revision: 0, category: "possible_human", status: "human_review_pending", priority: "review_required" };
    S.incidents.push(inc);
    log("Model 2", "assessment", `opens ${inc.id}: possible human at (${rep.x},${rep.y}) from ${rep.label}`, "warn");
  }
  inc.evidence.push(rep); const before = inc.sources.size; inc.sources.add(rep.drone);
  if (rep.conf < 0.5) inc.conflict++;
  if (inc.sources.size !== before || inc.revision === 0) {
    inc.revision++; S.model2.fused++;
    if (inc.sources.size >= 2) { inc.category = "uncertain_need"; inc.priority = hazardNear ? "potentially_urgent" : "elevated"; }
    else inc.priority = hazardNear ? "elevated" : "review_required";
    if (["approved", "rejected"].includes(inc.status) === false) inc.status = "human_review_pending";
    S.recs.filter((r) => r.inc === inc.id && r.status === "pending").forEach((r) => (r.status = "superseded"));
    const rec = { id: `REC-${inc.id.slice(4)}-v${inc.revision}`, inc: inc.id, version: inc.revision, status: "pending",
      request: inc.sources.size >= 2 ? "Review rescue need (corroborated by multiple drones)" : "Inspect evidence / request additional observation",
      unknowns: ["synthetic sensor report", "human verification required"] };
    S.recs.push(rec);
    S.model2.last = `${inc.id} rev ${inc.revision}: fused ${inc.sources.size} source(s), urgency ${inc.priority}`;
    log("Model 2", "fusion", `fuses ${inc.evidence.length} reports from ${inc.sources.size} drone(s) for ${inc.id} → ${inc.category}, urgency ${inc.priority}`, "info");
    log("Model 2", "recommendation", `creates ${rec.id} for human review`, "warn");
    pulse("m2", "human", "#f59e0b");
    toast(`New recommendation ${rec.id} awaiting human review`);
  } else log("Model 2", "fusion", `adds corroborating evidence to ${inc.id} (${inc.evidence.length} reports)`, "info");
}

function decide(recId, action) {
  const rec = S.recs.find((r) => r.id === recId); if (!rec || rec.status !== "pending") return;
  const inc = S.incidents.find((i) => i.id === rec.inc);
  if (action === "approve") { rec.status = "approved"; inc.status = "acknowledged"; log("Human coordinator", "oversight", `approves ${rec.id} (v${rec.version}) — validated by Model 2; rescue NOT confirmed`, "ok"); }
  if (action === "reject") { rec.status = "rejected"; inc.status = "rejected"; log("Human coordinator", "oversight", `rejects ${rec.id} (v${rec.version})`, "bad"); }
  if (action === "review") {
    rec.status = "revision_requested"; inc.status = "additional_observation_requested";
    const d = S.drones.reduce((a, b) => (Math.abs(a.x - inc.x) + Math.abs(a.y - inc.y) <= Math.abs(b.x - inc.x) + Math.abs(b.y - inc.y) ? a : b));
    d.path.splice(d.wp % d.path.length, 0, [inc.x, inc.y]); d.history.unshift(`t=${S.tick * 100}ms revisit ${inc.id}`);
    log("Human coordinator", "oversight", `requests additional review of ${inc.id}; Model 2 asks ${d.label} to re-observe`, "warn");
  }
  pulse("human", "m2", "#22c55e"); render();
}

function finish() { clearInterval(timer); timer = null; S.status = "Completed"; log("System", "mission", "Synthetic mission horizon reached", "ok"); render(); }
function start() { if (timer) return; if (S.status === "Completed") reset(); S.status = "Running"; log("System", "mission", "Simulation started", "ok"); run(); }
function run() { clearInterval(timer); timer = setInterval(step, 400 / +$("selSpeed").value); }
function pause() { if (!timer) return; clearInterval(timer); timer = null; S.status = "Paused"; log("System", "mission", "Simulation paused", "warn"); render(); }
function resume() { if (timer || S.status !== "Paused") return; S.status = "Running"; log("System", "mission", "Simulation resumed", "ok"); run(); render(); }
function stop() { clearInterval(timer); timer = null; S.status = "Stopped"; log("System", "mission", "Simulation stopped by coordinator", "bad"); render(); }

// ---------------- rendering ----------------
const svgNS = "http://www.w3.org/2000/svg";
function el(tag, attrs = {}, parent) { const e = document.createElementNS(svgNS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); parent && parent.appendChild(e); return e; }
const fmt = (ms) => { const s = ms / 1000; return `${String(Math.floor(s / 60)).padStart(2, "0")}:${(s % 60).toFixed(1).padStart(4, "0")}`; };
const cls = (s) => ({ ok: "ok", approved: "ok", connected: "ok", available: "ok", warn: "warn", pending: "warn", human_review_pending: "warn", bad: "bad", rejected: "bad", disconnected: "bad" }[s] || "info");

function renderMap() {
  const m = $("map"); m.innerHTML = "";
  const hzColor = SCEN[S.scen].color;
  for (let x = 0; x < W; x++) for (let y = 0; y < H; y++) {
    const t = S.terrain.get(key(x, y)), cov = S.coverage.get(key(x, y));
    let fill = cov ? (S.tick - cov > 15 ? "rgba(20,184,166,.12)" : "rgba(20,184,166,.28)") : "#0b1322";
    if (t === "building") fill = "#3b4a63"; else if (t === "base") fill = "#a78bfa";
    else if (t && cov) fill = hzColor; else if (t) fill = "#0b1322";
    el("rect", { x: x * C + 1, y: y * C + 1, width: C - 2, height: C - 2, rx: 4, fill, stroke: cov ? "#14b8a640" : "#1e293b", "stroke-dasharray": cov ? "" : "3 3" }, m);
    if (t && t !== "building" && t !== "base" && cov) el("text", { x: x * C + 25, y: y * C + 30, "text-anchor": "middle", fill: "#ffffffaa", "font-size": 9 }, m).textContent = t;
  }
  el("text", { x: 25, y: 4 * C + 30, "text-anchor": "middle", fill: "#fff", "font-size": 10, "font-weight": 700 }, m).textContent = "BASE";
  S.drones.forEach((d, i) => { // sector boundaries
    const x0 = +d.sector.split(" ")[1].split("-")[0];
    if (i) el("line", { x1: x0 * C, y1: 0, x2: x0 * C, y2: H * C, stroke: "#22d3ee30", "stroke-dasharray": "6 6" }, m);
  });
  for (const s of S.sightings.slice(-40)) el("circle", { cx: s.x * C + 25, cy: s.y * C + 25, r: 18, fill: "none", stroke: "#f59e0b55", "stroke-width": 1.5, "stroke-dasharray": "4 3" }, m);
  for (const inc of S.incidents) {
    const g = el("g", { style: "cursor:pointer", transform: `translate(${inc.x * C + 25},${inc.y * C + 25})` }, m);
    const col = inc.status === "acknowledged" ? "#22c55e" : inc.status === "rejected" ? "#64748b" : "#ef4444";
    el("circle", { r: 22, fill: "none", stroke: col, "stroke-opacity": .4, class: "pulse" }, g);
    el("rect", { x: -8, y: -8, width: 16, height: 16, transform: "rotate(45)", fill: col }, g);
    el("text", { y: -26, "text-anchor": "middle", fill: col, "font-size": 10, "font-weight": 700 }, g).textContent = inc.id;
    g.onclick = () => { S.selInc = inc.id; show("incidents"); };
  }
  for (const d of S.drones) {
    if (d.trail.length > 1) el("polyline", { points: d.trail.map(([x, y]) => `${x * C + 25},${y * C + 25}`).join(" "), fill: "none", stroke: "#22d3ee", "stroke-opacity": .35, "stroke-width": 2 }, m);
    const g = el("g", { transform: `translate(${d.x * C + 25},${d.y * C + 25})`, style: "cursor:pointer;transition:transform .35s linear" }, m);
    el("circle", { r: 16, fill: "#22d3ee18", stroke: d.comm === "connected" ? "#22d3ee" : "#ef4444", "stroke-dasharray": d.comm === "connected" ? "" : "3 2" }, g);
    [[-7, -7], [7, -7], [-7, 7], [7, 7]].forEach(([a, b]) => { el("line", { x1: 0, y1: 0, x2: a, y2: b, stroke: "#cffafe", "stroke-width": 2 }, g); el("circle", { cx: a, cy: b, r: 3.2, fill: "none", stroke: "#cffafe" }, g); });
    el("circle", { r: 3, fill: "#22d3ee" }, g);
    el("text", { y: 28, "text-anchor": "middle", fill: "#e0f2fe", "font-size": 9.5, "font-weight": 700 }, g).textContent = d.label.replace("Drone ", "D");
    g.onclick = () => { S.selDrone = d.key; show("fleet"); };
  }
  $("mapNote").textContent = `SYNTHETIC · local grid 12×10 cells · ±0.5 cell uncertainty · t=${fmt(S.tick * 100)}`;
}

function renderNet() {
  const n = $("net"); n.innerHTML = "";
  const pos = { m2: [300, 200], human: [300, 380] };
  S.drones.forEach((d, i) => { const a = (Math.PI * 2 * i) / S.drones.length - Math.PI / 2; pos[d.key] = [300 + 220 * Math.cos(a), 170 + 140 * Math.sin(a)]; });
  S.drones.forEach((d, i) => { const o = S.drones[(i + 1) % S.drones.length]; el("line", { x1: pos[d.key][0], y1: pos[d.key][1], x2: pos[o.key][0], y2: pos[o.key][1], stroke: "#a78bfa40", "stroke-dasharray": "4 4" }, n); });
  S.drones.forEach((d) => el("line", { x1: pos[d.key][0], y1: pos[d.key][1], x2: 300, y2: 200, stroke: S.comm.down ? "#ef444466" : "#22d3ee55", "stroke-width": 1.5, "stroke-dasharray": S.comm.down ? "3 4" : "" }, n));
  el("line", { x1: 300, y1: 200, x2: 300, y2: 380, stroke: "#f59e0b77", "stroke-width": 2 }, n);
  for (const p of S.pulses) { const a = pos[p.from], b = pos[p.to]; if (a && b) el("circle", { cx: a[0] + (b[0] - a[0]) * p.t, cy: a[1] + (b[1] - a[1]) * p.t, r: 4, fill: p.color }, n); }
  const node = (k, label, sub, col, r = 24) => { const [x, y] = pos[k]; el("circle", { cx: x, cy: y, r, fill: "#0f1b2e", stroke: col, "stroke-width": 2 }, n); el("text", { x, y: y + 4, "text-anchor": "middle", fill: "#fff", "font-size": 10, "font-weight": 700 }, n).textContent = label; if (sub) el("text", { x, y: y + r + 12, "text-anchor": "middle", fill: "#7f93ad", "font-size": 9 }, n).textContent = sub; };
  S.drones.forEach((d) => node(d.key, d.label.replace("Drone ", "D"), "Model 1", d.comm === "connected" ? "#22d3ee" : "#ef4444", 18));
  node("m2", "MODEL 2", "Central command", S.comm.down ? "#f59e0b" : "#14b8a6", 34);
  node("human", "HUMAN", "Rescue coordinator", "#f59e0b", 26);
  $("commStats").innerHTML = kv({
    "Drone → command link": badge(S.comm.down ? "INTERRUPTED" : "connected", S.comm.down ? "bad" : "ok"),
    "Messages sent": S.comm.sent, "Delivered to Model 2": S.comm.delivered, "Peer-to-peer messages": S.comm.peer,
    "Queued during outage": S.comm.queued, "Pending in queue": S.queue.length, "Recovery events": S.comm.recoveries,
    "Synthetic latency": S.comm.down ? "n/a (link down)" : "≈100 ms (1 tick)", "Planned outage": `t=${OUTAGE[0] / 10}s – ${OUTAGE[1] / 10}s (demo)`,
  }) + `<p class="note">Purple: peer-to-peer · Cyan: drone→Model 2 · Amber: Model 2→human · Green: human decision. Synthetic playback.</p>`;
}

const badge = (t, c) => `<span class="badge ${c || cls(t)}">${t}</span>`;
const kv = (o) => `<div class="kv">${Object.entries(o).map(([k, v]) => `<span>${k}</span><b>${v}</b>`).join("")}</div>`;

function droneCard(d) {
  return `<div class="dcard ${S.selDrone === d.key ? "sel" : ""}" data-drone="${d.key}"><h3>${d.label} ${badge(d.comm)}</h3>
  <div class="kv"><span>Activity</span><b>${d.activity}</b><span>Sector</span><b>${d.sector}</b><span>Position</span><b>(${d.x},${d.y}) ±0.5</b>
  <span>Observations</span><b>${d.obs}</b><span>Sensors</span><b>${d.sensors.length}/4 ok</b><span>Last report</span><b>${fmt(d.lastMs)}</b></div>
  <div class="bar" title="synthetic battery"><i style="width:${d.battery}%;background:${d.battery < 25 ? "#ef4444" : d.battery < 50 ? "#f59e0b" : "#22c55e"}"></i></div></div>`;
}

function recCard(r) {
  const inc = S.incidents.find((i) => i.id === r.inc);
  const acts = r.status === "pending" ? `<div class="acts"><button class="btn ok" data-dec="approve" data-rec="${r.id}">Approve</button><button class="btn bad" data-dec="reject" data-rec="${r.id}">Reject</button><button class="btn warn" data-dec="review" data-rec="${r.id}">Request additional review</button></div>` : "";
  return `<div class="rec"><h3>${r.id} <span>${badge(r.status)}</span></h3>
  ${kv({ Incident: `${inc.id} · ${inc.category}`, Version: `v${r.version}`, Request: r.request, Urgency: badge(inc.priority, inc.priority === "potentially_urgent" ? "bad" : "warn"),
    "Supporting evidence": `${inc.evidence.length} reports from ${inc.sources.size} drone(s)`, Contradictory: inc.conflict, Uncertainty: r.unknowns.join("; ") })}
  ${acts}<p class="note">Decision-support only. Approval records a human review; it does not confirm a rescue or move any drone.</p></div>`;
}

function render() {
  if (!S) return;
  $("tStatus").textContent = S.status; $("tTime").textContent = fmt(S.tick * 100);
  $("tModel2").innerHTML = `<i class="dot ${S.comm.down ? "warn" : "ok"}"></i>${S.model2.state}`;
  const pending = S.recs.filter((r) => r.status === "pending");
  const avail = S.drones.filter((d) => d.battery > 5).length;
  const open = S.incidents.filter((i) => !["rejected"].includes(i.status)).length;
  $("metrics").innerHTML = [
    ["Total drones", S.drones.length, "Model 1 agents", "#22d3ee"], ["Available drones", avail, "reported", "#22c55e"],
    ["Possible human sightings", S.sightings.length, "reports (unverified)", "#f59e0b"], ["Open incidents", open, "Model 2", "#ef4444"],
    ["Reported coverage", `${Math.round((100 * S.coverage.size) / (W * H))}%`, "reported cells", "#14b8a6"],
    ["Pending human reviews", pending.length, "awaiting coordinator", "#f59e0b"],
    ["Communication", S.comm.down ? "DEGRADED" : "Nominal", `${S.comm.sent} msgs`, S.comm.down ? "#ef4444" : "#22c55e"],
  ].map(([a, b, c, col]) => `<div class="metric" style="--c:${col}"><span>${a}</span><b>${b}</b><small>${c} · synthetic</small></div>`).join("");
  renderMap(); renderNet();
  $("m2Badge").className = `badge ${S.comm.down ? "warn" : "ok"}`; $("m2Badge").textContent = S.model2.state;
  $("m2Stats").innerHTML = [["Reports received", S.model2.reports], ["Fusion updates", S.model2.fused], ["Incidents", S.incidents.length],
    ["Pending review", pending.length], ["Queued (outage)", S.queue.length], ["Sources fused", new Set(S.incidents.flatMap((i) => [...i.sources])).size]]
    .map(([a, b]) => `<div class="m2s"><span>${a}</span><b>${b}</b></div>`).join("");
  $("m2Flow").innerHTML = `<div class="m2line">Latest: ${S.model2.last}</div>` + S.events.filter((e) => e.src === "Model 2").slice(0, 4).map((e) => `<div class="m2line">${e.text}</div>`).join("");
  $("feed").innerHTML = S.events.slice(0, 60).map((e) => `<li><span class="t">${fmt(e.ms)}</span><span><span class="src">${e.src}</span><br><span class="cat">${e.cat}</span></span><span>${e.text} ${badge(e.status)}</span></li>`).join("");
  $("feedNote").textContent = "synthetic playback events";
  $("fleetMini").innerHTML = S.drones.map(droneCard).join(""); $("fleetFull").innerHTML = S.drones.map(droneCard).join("");
  const recs = [...S.recs].reverse().filter((r) => r.status !== "superseded");
  $("reviewMini").innerHTML = pending.length ? pending.slice(-2).reverse().map(recCard).join("") : `<p class="muted">No recommendations awaiting review. Start the demo — Model 2 will create recommendations when drones report possible humans.</p>`;
  $("reviewFull").innerHTML = recs.length ? recs.map(recCard).join("") : `<p class="muted">No recommendations yet.</p>`;
  const d = S.drones.find((x) => x.key === S.selDrone);
  $("droneDetail").innerHTML = d ? `<h3>${d.label} · Model 1 agent</h3>${kv({ Availability: badge(d.avail), Communication: badge(d.comm), Activity: d.activity, Sector: d.sector, Position: `(${d.x},${d.y}) ±0.5 cell`, "Battery (synthetic)": `${d.battery.toFixed(0)}%`, Sensors: d.sensors.join(", "), Observations: d.obs })}
    <h3 style="margin-top:10px">Recent observations</h3>${d.recent.map((o) => `<div class="m2line">${fmt(o.ms)} · ${o.kind}${o.tag ? " (" + o.tag + ")" : ""} at (${o.x},${o.y}) conf ${o.conf}</div>`).join("") || "<p class='muted'>none</p>"}
    <h3 style="margin-top:10px">Task history</h3>${[`sector sweep ${d.sector}`, ...d.history].map((h) => `<div class="m2line">${h}</div>`).join("")}` : "Select a drone on the map or in the fleet list.";
  $("incTable").innerHTML = `<tr><th>ID</th><th>Category</th><th>Location</th><th>Sources</th><th>Evidence</th><th>Urgency</th><th>Status</th></tr>` + S.incidents.map((i) => `<tr class="click ${S.selInc === i.id ? "sel" : ""}" data-inc="${i.id}"><td>${i.id}</td><td>${i.category}</td><td>(${i.x},${i.y}) ±0.5</td><td>${[...i.sources].map((s) => "D" + String(+s.slice(1) + 1).padStart(2, "0")).join(", ")}</td><td>${i.evidence.length} / ${i.conflict} contra</td><td>${badge(i.priority, i.priority === "potentially_urgent" ? "bad" : "warn")}</td><td>${badge(i.status)}</td></tr>`).join("");
  const inc = S.incidents.find((i) => i.id === S.selInc);
  $("incDetail").innerHTML = inc ? `<h3>${inc.id}</h3>${kv({ Category: inc.category === "uncertain_need" ? "Corroborated possible human — NOT confirmed" : "Possible human — unverified", "Estimated location": `(${inc.x},${inc.y}) ±0.5 cell`, Revision: inc.revision, "Source drones": inc.sources.size, "Supporting evidence": inc.evidence.length, "Contradictory (low-confidence)": inc.conflict, Urgency: inc.priority, Status: badge(inc.status) })}
    <h3 style="margin-top:10px">Evidence</h3>${inc.evidence.slice(-8).map((o) => `<div class="m2line">${fmt(o.ms)} · ${o.label} · conf ${o.conf}</div>`).join("")}` : "Select an incident.";
  const obs = S.drones.flatMap((x) => x.recent).sort((a, b) => b.ms - a.ms).slice(0, 40);
  $("obsTable").innerHTML = `<tr><th>Time</th><th>Drone</th><th>Kind</th><th>Cell</th><th>Confidence</th><th>Artifact</th></tr>` + obs.map((o) => `<tr><td>${fmt(o.ms)}</td><td>${o.label}</td><td>${o.kind}${o.tag ? " · " + o.tag : ""}</td><td>(${o.x},${o.y})</td><td>${o.conf}</td><td class="muted">synthetic/${o.id}</td></tr>`).join("");
  renderCharts(); renderHealth();
}

function chart(title, values, color, fmtv = (v) => v) {
  const w = 300, h = 120, max = Math.max(1, ...values), pts = values.map((v, i) => `${(i / Math.max(1, values.length - 1)) * w},${h - (v / max) * (h - 10)}`).join(" ");
  return `<div class="card chart"><div class="cardhead"><h2>${title}</h2><span class="muted">${values.length ? fmtv(values[values.length - 1]) : "-"} · synthetic</span></div>
  <svg viewBox="0 0 ${w} ${h + 5}" preserveAspectRatio="none"><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2"/><polyline points="0,${h} ${pts} ${w},${h}" fill="${color}22" stroke="none"/></svg></div>`;
}
function renderCharts() {
  const s = S.series;
  const done = S.recs.filter((r) => ["approved", "rejected"].includes(r.status)).length;
  $("charts").innerHTML = chart("Reported search coverage", s.map((x) => x.cov * 100), "#14b8a6", (v) => v.toFixed(0) + "%") + chart("Observations reported", s.map((x) => x.obs), "#22d3ee") +
    chart("Drone availability", s.map((x) => x.avail), "#22c55e") + chart("Communication activity (messages)", s.map((x) => x.msgs), "#a78bfa") +
    chart("Incident count", s.map((x) => x.inc), "#ef4444") + `<div class="card chart"><div class="cardhead"><h2>Review / task completion</h2></div>${kv({ "Recommendations created": S.recs.length, "Human decisions": done, "Pending": S.recs.filter((r) => r.status === "pending").length, "Sector sweep progress": Math.round((100 * S.coverage.size) / (W * H)) + "% reported" })}<p class="note">Synthetic demonstration metrics — not research results.</p></div>`;
}
function renderHealth() {
  $("health").innerHTML = kv({ "Dashboard mode": badge("Synthetic Demo", "warn"), "Simulation engine": "local deterministic playback (seed 42)", "Model 2 (synthetic)": badge(S.model2.state), "Backend API": $("tBackend").innerText,
    "Drones reporting": `${S.drones.filter((d) => d.comm === "connected").length}/${S.drones.length}`, "Event feed size": S.events.length }) + `<p class="note">Phase 7 backend (FastAPI) is integrated separately; this mode never presents synthetic data as backend results.</p>`;
}

function show(view) {
  document.querySelectorAll("#nav button").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.dataset.view.split(" ").includes(view)));
  render();
}
function toast(msg) { const t = document.createElement("div"); t.className = "toast"; t.textContent = msg; $("toast").appendChild(t); setTimeout(() => t.remove(), 3500); }

document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-dec],[data-drone],[data-inc],#nav button");
  if (!t) return;
  if (t.dataset.dec) decide(t.dataset.rec, t.dataset.dec);
  else if (t.dataset.drone) { S.selDrone = t.dataset.drone; show("fleet"); }
  else if (t.dataset.inc) { S.selInc = t.dataset.inc; render(); }
  else if (t.dataset.view) show(t.dataset.view);
});
$("btnDemo").onclick = () => { $("selScenario").value = "flood_basic"; $("selDrones").value = "6"; reset(); start(); toast("Synthetic six-drone flood demo running"); };
$("btnStart").onclick = start; $("btnPause").onclick = pause; $("btnResume").onclick = resume; $("btnStop").onclick = stop; $("btnReset").onclick = () => { reset(); toast("Demo reset"); };
$("selSpeed").onchange = () => timer && run();
$("selScenario").onchange = $("selDrones").onchange = () => { if (!timer) reset(); };
$("selMode").onchange = () => { if ($("selMode").value === "connected") { toast("Connected mode: start the backend (see README). Synthetic mode stays active."); $("selMode").value = "synthetic"; } };

async function checkBackend() {
  try { const r = await fetch("http://127.0.0.1:8000/health/ready", { cache: "no-store" }); $("tBackend").innerHTML = `<i class="dot ${r.ok ? "ok" : "warn"}"></i>${r.ok ? "online" : "not ready"}`; }
  catch { $("tBackend").innerHTML = `<i class="dot bad"></i>offline`; }
}
reset(); checkBackend(); setInterval(checkBackend, 5000);
