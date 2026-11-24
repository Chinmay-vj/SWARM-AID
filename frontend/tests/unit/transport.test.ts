import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";
import { ApiClient, type TokenStore } from "../../src/services/api/client";
import { openMissionStream, backoffDelay } from "../../src/services/websocket/missionStream";
import type { MissionEvent, TokenResponse } from "../../src/contracts/api";

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function tokens(initial = "old"): TokenStore & { current: string | null; expiredCalls: number } {
  return {
    current: initial,
    expiredCalls: 0,
    access() {
      return this.current;
    },
    refresh() {
      return "refresh-1";
    },
    update(t: TokenResponse) {
      this.current = t.access_token;
    },
    expired() {
      this.current = null;
      this.expiredCalls++;
    },
  };
}

const pair = {
  access_token: "new",
  refresh_token: "r2",
  token_type: "bearer",
  access_expires_at: "2026-11-24T14:00:00Z",
  refresh_expires_at: "2026-11-25T02:00:00Z",
};

describe("ApiClient", () => {
  it("sends bearer, request id and validates responses", async () => {
    const fetchImpl = vi.fn(async (_u: RequestInfo | URL, init?: RequestInit) => {
      const h = init!.headers as Record<string, string>;
      expect(h.Authorization).toBe("Bearer old");
      expect(h["X-Request-ID"]).toMatch(/^ui-[A-Za-z0-9]{8,}$/);
      return json(200, { ok: true });
    });
    const c = new ApiClient({ tokens: tokens(), fetchImpl: fetchImpl as typeof fetch });
    await expect(c.request("/x", { schema: z.object({ ok: z.boolean() }) })).resolves.toEqual({ ok: true });
  });

  it("raises schema errors for incompatible responses", async () => {
    const c = new ApiClient({
      tokens: tokens(),
      fetchImpl: (async () => json(200, { ok: "yes" })) as typeof fetch,
    });
    await expect(c.request("/x", { schema: z.object({ ok: z.boolean() }) })).rejects.toMatchObject({
      kind: "schema",
    });
  });

  it("maps structured backend errors", async () => {
    const c = new ApiClient({
      tokens: tokens(),
      fetchImpl: (async () =>
        json(409, {
          error: {
            code: "stale_version",
            message: "recommendation version is outdated",
            request_id: "abc",
            details: { submitted_version: 1 },
          },
        })) as typeof fetch,
    });
    await expect(c.request("/x", { method: "POST", body: {} })).rejects.toMatchObject({
      kind: "conflict",
      code: "stale_version",
      requestId: "abc",
    });
  });

  it("refreshes once on 401 with a single flight and retries", async () => {
    const t = tokens();
    let refreshes = 0;
    const fetchImpl = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      if (String(url).endsWith("/auth/refresh")) {
        refreshes++;
        return json(200, pair);
      }
      const h = init!.headers as Record<string, string>;
      return h.Authorization === "Bearer new"
        ? json(200, { ok: true })
        : json(401, { error: { code: "invalid_token", message: "expired", request_id: "r" } });
    });
    const c = new ApiClient({ tokens: t, fetchImpl: fetchImpl as typeof fetch });
    const results = await Promise.all([c.request("/a"), c.request("/b")]);
    expect(results).toEqual([{ ok: true }, { ok: true }]);
    expect(refreshes).toBe(1);
  });

  it("expires the session when refresh fails", async () => {
    const t = tokens();
    const c = new ApiClient({
      tokens: t,
      fetchImpl: (async () =>
        json(401, { error: { code: "x", message: "no", request_id: "r" } })) as typeof fetch,
    });
    await expect(c.request("/a")).rejects.toMatchObject({ kind: "unauthenticated" });
    expect(t.expiredCalls).toBe(1);
  });

  it("retries idempotent GETs on network errors but never mutations", async () => {
    let calls = 0;
    const failing = (async () => {
      calls++;
      throw new TypeError("Failed to fetch");
    }) as typeof fetch;
    const c = new ApiClient({ tokens: tokens(), fetchImpl: failing });
    await expect(c.request("/m", { method: "POST", body: {} })).rejects.toMatchObject({ kind: "network" });
    expect(calls).toBe(1);
    calls = 0;
    await expect(c.request("/g", { retries: 1 })).rejects.toMatchObject({ kind: "network" });
    expect(calls).toBe(2);
  });

  it("times out", async () => {
    const hanging = ((_u: RequestInfo | URL, init?: RequestInit) =>
      new Promise((_r, reject) =>
        init!.signal!.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))),
      )) as typeof fetch;
    const c = new ApiClient({ tokens: tokens(), fetchImpl: hanging, timeoutMs: 20 });
    await expect(c.request("/slow", { retries: 0 })).rejects.toMatchObject({ kind: "timeout" });
  });

  it("supports caller cancellation", async () => {
    const hanging = ((_u: RequestInfo | URL, init?: RequestInit) =>
      new Promise((_r, reject) =>
        init!.signal!.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))),
      )) as typeof fetch;
    const c = new ApiClient({ tokens: tokens(), fetchImpl: hanging, timeoutMs: 5000 });
    const ctrl = new AbortController();
    const p = c.request("/slow", { signal: ctrl.signal });
    ctrl.abort();
    await expect(p).rejects.toMatchObject({ kind: "aborted" });
  });
});

class FakeSocket {
  static instances: FakeSocket[] = [];
  readyState = 0;
  sent: Record<string, unknown>[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(readonly url: string) {
    FakeSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(JSON.parse(data) as Record<string, unknown>);
  }
  close(code = 1000) {
    this.readyState = 3;
    this.onclose?.({ code });
  }
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
  receive(frame: unknown) {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }
}

const event = (sequence: number): MissionEvent => ({
  id: `e${sequence}`,
  mission_id: "m",
  sequence,
  event_type: "OBSERVATION_RECEIVED",
  schema_version: "1",
  source: "command",
  occurred_at: "2026-11-24T13:25:42Z",
  sim_time_ms: sequence * 100,
  correlation_id: "c",
  resource_type: "observation",
  resource_id: `o${sequence}`,
  payload: {},
});

describe("mission stream", () => {
  beforeEach(() => {
    FakeSocket.instances = [];
    vi.useFakeTimers();
  });
  afterEach(() => vi.useRealTimers());

  const setup = (overrides: Partial<Parameters<typeof openMissionStream>[2]> = {}) => {
    const received: number[] = [];
    const statuses: string[] = [];
    const resyncs: number[] = [];
    const sub = openMissionStream(
      0,
      {
        onEvent: (e) => received.push(e.sequence),
        onStatus: (s) => statuses.push(s),
        onResync: (n) => resyncs.push(n),
      },
      {
        url: "ws://x/ws/v1/missions/m",
        token: () => "tok",
        refresh: async () => true,
        poll: async () => [],
        WebSocketImpl: FakeSocket as unknown as typeof WebSocket,
        ...overrides,
      },
    );
    return { received, statuses, resyncs, sub };
  };

  it("authenticates in the first frame (never in the URL) and subscribes from the cursor", () => {
    const { statuses } = setup();
    const ws = FakeSocket.instances[0]!;
    expect(ws.url).not.toContain("tok");
    ws.open();
    expect(ws.sent[0]).toEqual({ type: "auth", token: "tok" });
    ws.receive({ type: "welcome", last_sequence: 5, heartbeat_seconds: 15 });
    expect(ws.sent[1]).toEqual({ type: "subscribe", after_sequence: 0 });
    ws.receive({ type: "subscribed", topics: [] });
    expect(statuses).toContain("open");
  });

  it("deduplicates, orders and ignores malformed events", () => {
    const { received } = setup();
    const ws = FakeSocket.instances[0]!;
    ws.open();
    ws.receive({ type: "event", event: event(1) });
    ws.receive({ type: "event", event: event(1) });
    ws.receive({ type: "event", event: event(3) });
    ws.receive({ type: "event", event: { bad: true } });
    ws.receive({ type: "event", event: event(2) });
    expect(received).toEqual([1, 2, 3]);
  });

  it("reconnects with backoff and resumes after the last applied sequence", () => {
    setup();
    const first = FakeSocket.instances[0]!;
    first.open();
    first.receive({ type: "event", event: event(1) });
    first.close(1006);
    vi.advanceTimersByTime(1100);
    const second = FakeSocket.instances[1]!;
    second.open();
    second.receive({ type: "welcome", last_sequence: 1 });
    expect(second.sent[1]).toEqual({ type: "subscribe", after_sequence: 1 });
  });

  it("requests resynchronization when the server says the client fell behind", () => {
    const { resyncs } = setup();
    const ws = FakeSocket.instances[0]!;
    ws.open();
    ws.receive({ type: "event", event: event(1) });
    ws.receive({ type: "resync_required", last_delivered_sequence: 1 });
    expect(resyncs).toEqual([1]);
  });

  it("stops on forbidden and falls back to polling after repeated failures", async () => {
    const forbidden = setup();
    FakeSocket.instances[0]!.close(4403);
    expect(forbidden.statuses.at(-1)).toBe("failed");
    forbidden.sub.close();

    FakeSocket.instances = [];
    const polled: number[] = [];
    const flaky = setup({ poll: async (after) => (polled.push(after), [event(1)]), pollAfterFailures: 2 });
    FakeSocket.instances[0]!.close(1006);
    vi.advanceTimersByTime(1100);
    FakeSocket.instances[1]!.close(1006);
    await vi.advanceTimersByTimeAsync(10);
    expect(flaky.statuses).toContain("polling");
    expect(polled.length).toBeGreaterThan(0);
    expect(flaky.received).toEqual([1]);
    flaky.sub.close();
  });

  it("cleans up on close", () => {
    const { sub, statuses } = setup();
    sub.close();
    expect(statuses.at(-1)).toBe("closed");
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.instances).toHaveLength(1);
  });

  it("bounds backoff with jitter", () => {
    expect(backoffDelay(1, 30_000, () => 0)).toBe(500);
    expect(backoffDelay(10, 30_000, () => 1)).toBe(30_000);
  });
});
