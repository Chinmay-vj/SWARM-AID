/**
 * Centralized HTTP transport for the Phase 7 backend.
 *
 *  - Same-origin by default (Vite proxy), configurable with VITE_API_BASE_URL.
 *  - Bearer access token held in memory; one single-flight refresh on 401, then retry once.
 *  - Timeouts and caller cancellation via AbortSignal.
 *  - X-Request-ID correlation header on every request (echoed by the backend).
 *  - Runtime validation of every JSON response with the zod contract.
 *  - Safe retries only for idempotent GETs. Mutations are never retried automatically.
 */
import type { z } from "zod";
import { ErrorResponseSchema, TokenResponseSchema, type TokenResponse } from "../../contracts/api";
import { ApiError, kindForStatus } from "./errors";

export interface TokenStore {
  access(): string | null;
  refresh(): string | null;
  update(tokens: TokenResponse): void;
  expired(): void;
}

export interface ClientOptions {
  baseUrl?: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
  tokens: TokenStore;
  /** Called with request outcome for client-side API latency/error metrics. */
  observe?: (sample: { method: string; path: string; status: number | null; ms: number }) => void;
}

export interface RequestOptions<T> {
  method?: "GET" | "POST" | "PATCH";
  query?: Record<string, string | number | boolean | null | undefined>;
  body?: unknown;
  schema?: z.ZodType<T>;
  signal?: AbortSignal;
  auth?: boolean;
  /** Raw text response (CSV export). */
  text?: boolean;
  /** Binary response (evidence content). */
  blob?: boolean;
  retries?: number;
}

function requestId(): string {
  const raw =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}${Math.random()}`;
  return `ui-${raw.replace(/[^A-Za-z0-9]/g, "").slice(0, 24)}`;
}

export class ApiClient {
  readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly fetchImpl: typeof fetch;
  private refreshing: Promise<boolean> | null = null;

  constructor(private readonly options: ClientOptions) {
    this.baseUrl = (options.baseUrl ?? "").replace(/\/$/, "");
    this.timeoutMs = options.timeoutMs ?? 15000;
    this.fetchImpl = options.fetchImpl ?? ((...args) => fetch(...args));
  }

  url(path: string, query?: RequestOptions<unknown>["query"]): string {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(query ?? {})) {
      if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
    }
    const qs = params.toString();
    return `${this.baseUrl}${path}${qs ? `?${qs}` : ""}`;
  }

  async request<T>(path: string, opts: RequestOptions<T> = {}): Promise<T> {
    const method = opts.method ?? "GET";
    const retries = method === "GET" ? (opts.retries ?? 1) : 0;
    let attempt = 0;
    for (;;) {
      try {
        return await this.once(path, opts, method, true);
      } catch (e) {
        if (e instanceof ApiError && e.retryable && attempt < retries && !opts.signal?.aborted) {
          attempt++;
          await new Promise((r) => setTimeout(r, 300 * 2 ** attempt));
          continue;
        }
        throw e;
      }
    }
  }

  private async once<T>(
    path: string,
    opts: RequestOptions<T>,
    method: string,
    allowRefresh: boolean,
  ): Promise<T> {
    const headers: Record<string, string> = {
      Accept: opts.text ? "text/csv, application/json" : "application/json",
      "X-Request-ID": requestId(),
    };
    const auth = opts.auth ?? true;
    const token = this.options.tokens.access();
    if (auth && token) headers.Authorization = `Bearer ${token}`;
    if (opts.body !== undefined) headers["Content-Type"] = "application/json";

    const controller = new AbortController();
    const timer = setTimeout(
      () => controller.abort(new DOMException("timeout", "TimeoutError")),
      this.timeoutMs,
    );
    const onAbort = () => controller.abort(opts.signal?.reason);
    opts.signal?.addEventListener("abort", onAbort, { once: true });
    const started = performance.now();
    let response: Response;
    try {
      response = await this.fetchImpl(this.url(path, opts.query), {
        method,
        headers,
        body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
        signal: controller.signal,
        credentials: "same-origin",
        cache: "no-store",
      });
    } catch (e) {
      this.options.observe?.({ method, path, status: null, ms: performance.now() - started });
      if (opts.signal?.aborted) throw new ApiError("aborted", "Request cancelled");
      if (controller.signal.aborted) throw new ApiError("timeout", "Request timed out");
      throw new ApiError("network", e instanceof Error ? e.message : "Network error");
    } finally {
      clearTimeout(timer);
      opts.signal?.removeEventListener("abort", onAbort);
    }
    this.options.observe?.({ method, path, status: response.status, ms: performance.now() - started });

    if (response.status === 401 && auth && allowRefresh && this.options.tokens.refresh()) {
      if (await this.refreshTokens()) return this.once(path, opts, method, false);
    }
    if (!response.ok) throw await this.toError(response);
    if (response.status === 204) return undefined as T;
    if (opts.text) return (await response.text()) as T;
    if (opts.blob) return (await response.blob()) as T;
    let json: unknown;
    try {
      json = await response.json();
    } catch {
      throw new ApiError(
        "schema",
        "Response was not valid JSON",
        response.status,
        null,
        response.headers.get("x-request-id"),
      );
    }
    if (!opts.schema) return json as T;
    const parsed = opts.schema.safeParse(json);
    if (!parsed.success) {
      if (import.meta.env.DEV)
        console.warn(`Contract mismatch for ${method} ${path}`, parsed.error.issues.slice(0, 5));
      throw new ApiError(
        "schema",
        `Response for ${path} did not match the expected contract`,
        response.status,
        "schema_mismatch",
        response.headers.get("x-request-id"),
        parsed.error.issues.slice(0, 5).map((i) => ({ path: i.path.join("."), message: i.message })),
      );
    }
    return parsed.data;
  }

  private async toError(response: Response): Promise<ApiError> {
    const kind = kindForStatus(response.status);
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      /* non-JSON error body */
    }
    const parsed = ErrorResponseSchema.safeParse(body);
    if (parsed.success) {
      const e = parsed.data.error;
      return new ApiError(kind, e.message, response.status, e.code, e.request_id, e.details ?? null);
    }
    return new ApiError(
      kind,
      `HTTP ${response.status}`,
      response.status,
      null,
      response.headers.get("x-request-id"),
    );
  }

  /** Single-flight refresh-token rotation. Concurrent 401s share one refresh request. */
  refreshTokens(): Promise<boolean> {
    if (this.refreshing) return this.refreshing;
    const refreshToken = this.options.tokens.refresh();
    if (!refreshToken) return Promise.resolve(false);
    this.refreshing = (async () => {
      try {
        const tokens = await this.once(
          "/api/v1/auth/refresh",
          { method: "POST", body: { refresh_token: refreshToken }, schema: TokenResponseSchema, auth: false },
          "POST",
          false,
        );
        this.options.tokens.update(tokens);
        return true;
      } catch {
        this.options.tokens.expired();
        return false;
      } finally {
        this.refreshing = null;
      }
    })();
    return this.refreshing;
  }
}
