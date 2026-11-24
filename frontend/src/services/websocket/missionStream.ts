/**
 * Mission event stream for /ws/v1/missions/{id} (backend/realtime/hub.py).
 *
 * Protocol: first frame {"type":"auth","token"} (never in the URL) → "welcome" →
 * {"type":"subscribe","after_sequence":n} replays the backlog, then ordered "event" frames,
 * periodic "heartbeat" frames, and "resync_required" + close 4008 when the client falls behind.
 *
 * This client:
 *  - de-duplicates and orders by per-mission sequence (EventBuffer),
 *  - reconnects with exponential backoff and jitter, resuming from the last applied sequence,
 *  - treats silence longer than 2.5× the heartbeat interval as a dead connection,
 *  - on 4401 refreshes the access token once before reconnecting,
 *  - on 4403 stops (authorization revoked) and reports "failed",
 *  - falls back to REST polling of GET /missions/{id}/events while the socket is down,
 *    reported to the UI as status "polling".
 */
import { EventSchema, type MissionEvent } from "../../contracts/api";
import { EventBuffer } from "../../lib/eventBuffer";
import type { StreamHandlers, Subscription } from "../providers/types";

export interface StreamOptions {
  url: string;
  token: () => string | null;
  refresh: () => Promise<boolean>;
  poll: (after: number) => Promise<MissionEvent[]>;
  WebSocketImpl?: typeof WebSocket;
  pollIntervalMs?: number;
  maxBackoffMs?: number;
  pollAfterFailures?: number;
}

const CLOSE_UNAUTHENTICATED = 4401;
const CLOSE_FORBIDDEN = 4403;
const CLOSE_SLOW = 4008;

export function backoffDelay(attempt: number, maxMs = 30_000, random: () => number = Math.random): number {
  const base = Math.min(maxMs, 1000 * 2 ** Math.max(0, attempt - 1));
  return Math.round(base / 2 + (random() * base) / 2);
}

export function openMissionStream(
  afterSequence: number,
  handlers: StreamHandlers,
  options: StreamOptions,
): Subscription {
  const WS = options.WebSocketImpl ?? WebSocket;
  const buffer = new EventBuffer<MissionEvent>(afterSequence, 200);
  let socket: WebSocket | null = null;
  let closed = false;
  let attempt = 0;
  let failures = 0;
  let refreshedForAuth = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let watchdog: ReturnType<typeof setTimeout> | null = null;
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let heartbeatMs = 15_000;

  const deliver = (events: MissionEvent[]) => events.forEach((e) => handlers.onEvent(e));

  const offer = (raw: unknown) => {
    const parsed = EventSchema.safeParse(raw);
    if (!parsed.success) return; // malformed frame: ignored, never rendered
    const result = buffer.offer(parsed.data);
    if (result.kind === "applied") deliver(result.events);
    else if (result.kind === "gap") {
      handlers.onResync(buffer.lastApplied);
      void pollOnce();
    }
  };

  const armWatchdog = () => {
    if (watchdog) clearTimeout(watchdog);
    watchdog = setTimeout(() => socket?.close(4000, "heartbeat timeout"), heartbeatMs * 2.5);
  };

  async function pollOnce() {
    try {
      const events = await options.poll(buffer.lastApplied);
      deliver(buffer.replay(events));
    } catch {
      /* polling failure is reflected by status; next interval retries */
    }
  }

  const startPolling = () => {
    if (pollTimer || closed) return;
    handlers.onStatus("polling", "WebSocket unavailable; polling the REST event feed");
    void pollOnce();
    pollTimer = setInterval(() => void pollOnce(), options.pollIntervalMs ?? 3000);
  };
  const stopPolling = () => {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
  };

  const schedule = () => {
    if (closed) return;
    attempt++;
    failures++;
    if (failures >= (options.pollAfterFailures ?? 3)) startPolling();
    else handlers.onStatus("reconnecting", `retry ${attempt}`);
    reconnectTimer = setTimeout(connect, backoffDelay(attempt, options.maxBackoffMs));
  };

  function connect() {
    if (closed) return;
    const token = options.token();
    if (!token) {
      handlers.onStatus("failed", "not authenticated");
      return;
    }
    handlers.onStatus(attempt === 0 ? "connecting" : "reconnecting");
    let ws: WebSocket;
    try {
      ws = new WS(options.url);
    } catch {
      schedule();
      return;
    }
    socket = ws;
    ws.onopen = () => ws.send(JSON.stringify({ type: "auth", token }));
    ws.onmessage = (message) => {
      armWatchdog();
      let frame: Record<string, unknown>;
      try {
        frame = JSON.parse(String(message.data)) as Record<string, unknown>;
      } catch {
        return;
      }
      switch (frame.type) {
        case "welcome":
          if (typeof frame.heartbeat_seconds === "number") heartbeatMs = frame.heartbeat_seconds * 1000;
          ws.send(JSON.stringify({ type: "subscribe", after_sequence: buffer.lastApplied }));
          break;
        case "subscribed":
          attempt = 0;
          failures = 0;
          refreshedForAuth = false;
          stopPolling();
          handlers.onStatus("open");
          break;
        case "event":
          offer(frame.event);
          break;
        case "heartbeat":
          if (typeof frame.last_sequence === "number" && frame.last_sequence > buffer.lastApplied + 50) {
            handlers.onResync(buffer.lastApplied);
            void pollOnce();
          }
          break;
        case "resync_required":
          handlers.onResync(buffer.lastApplied);
          break;
        default:
          break;
      }
    };
    ws.onclose = (event) => {
      if (watchdog) clearTimeout(watchdog);
      if (socket === ws) socket = null;
      if (closed) return;
      if (event.code === CLOSE_FORBIDDEN) {
        stopPolling();
        handlers.onStatus("failed", "authorization expired or mission not available");
        return;
      }
      if (event.code === CLOSE_UNAUTHENTICATED) {
        if (refreshedForAuth) {
          handlers.onStatus("failed", "authentication rejected");
          return;
        }
        refreshedForAuth = true;
        void options
          .refresh()
          .then((ok) => (ok ? schedule() : handlers.onStatus("failed", "session expired")));
        return;
      }
      if (event.code === CLOSE_SLOW) {
        handlers.onResync(buffer.lastApplied);
        void pollOnce();
      }
      schedule();
    };
    ws.onerror = () => {
      /* onclose follows and handles reconnection */
    };
  }

  connect();

  return {
    close() {
      closed = true;
      stopPolling();
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (watchdog) clearTimeout(watchdog);
      const ws = socket;
      socket = null;
      if (ws && ws.readyState <= 1) ws.close(1000, "client closed");
      handlers.onStatus("closed");
    },
    reconnect() {
      if (closed) return;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      attempt = 0;
      failures = 0;
      refreshedForAuth = false;
      const ws = socket;
      socket = null;
      if (ws) {
        ws.onclose = null;
        ws.close(1000, "manual reconnect");
      }
      connect();
    },
  };
}
