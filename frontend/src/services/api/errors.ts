/**
 * Structured client errors. Messages shown to users come from the backend's structured error
 * body (code + message) or fixed client text; raw responses and stack traces are never shown.
 */
export type ErrorKind =
  | "network" // backend unreachable
  | "timeout"
  | "aborted"
  | "unauthenticated" // 401
  | "forbidden" // 403
  | "not_found" // 404 (also returned for missions the user may not see)
  | "conflict" // 409 (stale version, duplicate, not pending ...)
  | "validation" // 422
  | "rate_limited" // 429
  | "server" // 5xx
  | "schema" // response did not match the contract
  | "unavailable" // capability not available in this data source
  | "http";

export class ApiError extends Error {
  constructor(
    readonly kind: ErrorKind,
    message: string,
    readonly status: number | null = null,
    readonly code: string | null = null,
    readonly requestId: string | null = null,
    readonly details: unknown = null,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get retryable(): boolean {
    return (
      this.kind === "network" ||
      this.kind === "timeout" ||
      this.kind === "server" ||
      this.kind === "rate_limited"
    );
  }

  /** Short user-facing text. */
  get userMessage(): string {
    switch (this.kind) {
      case "network":
        return "The backend could not be reached.";
      case "timeout":
        return "The backend did not respond in time.";
      case "unauthenticated":
        return "Your session has expired. Sign in again.";
      case "forbidden":
        return "You are not permitted to do this. The backend refused the request.";
      case "not_found":
        return "This resource does not exist or is not visible to you.";
      case "schema":
        return "The backend response did not match the dashboard contract.";
      case "unavailable":
        return this.message;
      default:
        return this.message || "Request failed.";
    }
  }
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError;
}

export function asApiError(e: unknown): ApiError {
  if (e instanceof ApiError) return e;
  if (e instanceof Error) return new ApiError("http", e.message);
  return new ApiError("http", "Unexpected error");
}

export function kindForStatus(status: number): ErrorKind {
  if (status === 401) return "unauthenticated";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  if (status === 409) return "conflict";
  if (status === 422) return "validation";
  if (status === 429) return "rate_limited";
  if (status >= 500) return "server";
  return "http";
}

export function unavailable(capability: string): ApiError {
  return new ApiError(
    "unavailable",
    `${capability} is not available in this data source.`,
    null,
    "unavailable",
  );
}
