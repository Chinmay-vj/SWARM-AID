/** Loading, empty, error and stale-data states. */
import { AlertTriangle, CircleSlash, Info, RefreshCw, ShieldAlert, WifiOff } from "lucide-react";
import type { ReactNode } from "react";
import { asApiError } from "../../services/api/errors";
import { Button } from "./primitives";

export function Skeleton({ rows = 3, height = 14 }: { rows?: number; height?: number }) {
  return (
    <div className="stack tight" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading…</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton" style={{ height, width: `${90 - i * 12}%` }} />
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  children,
  icon,
}: {
  title: string;
  children?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="state" role="status">
      {icon ?? <CircleSlash size={22} aria-hidden="true" />}
      <h3>{title}</h3>
      {children && <div>{children}</div>}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  title,
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
}) {
  const e = asApiError(error);
  const Icon =
    e.kind === "network" || e.kind === "timeout"
      ? WifiOff
      : e.kind === "forbidden"
        ? ShieldAlert
        : e.kind === "unavailable"
          ? Info
          : AlertTriangle;
  return (
    <div className="state" role="alert">
      <Icon size={22} aria-hidden="true" />
      <h3>{title ?? (e.kind === "unavailable" ? "Not available" : "Could not load this information")}</h3>
      <p>{e.userMessage}</p>
      {e.code && e.kind !== "unavailable" && (
        <p className="xs">
          code <code>{e.code}</code>
          {e.requestId ? (
            <>
              {" "}
              · request <code>{e.requestId}</code>
            </>
          ) : null}
        </p>
      )}
      {onRetry && e.kind !== "forbidden" && e.kind !== "unavailable" && (
        <Button icon={<RefreshCw size={14} aria-hidden="true" />} onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function AlertBox({
  tone,
  title,
  children,
  actions,
}: {
  tone: "ok" | "warn" | "bad" | "info";
  title?: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  const Icon = tone === "bad" ? AlertTriangle : tone === "warn" ? AlertTriangle : Info;
  return (
    <div className={`alert tone-${tone}`} role={tone === "bad" ? "alert" : "status"}>
      <Icon size={16} aria-hidden="true" style={{ marginTop: 2, flexShrink: 0 }} />
      <div className="alert-body">
        {title && <b>{title} </b>}
        {children}
      </div>
      {actions}
    </div>
  );
}

/**
 * Generic query renderer: loading → skeleton, error with no data → error state, error with
 * cached data → stale banner above the last known data.
 */
export function QueryView<T>({
  query,
  children,
  empty,
  isEmpty,
  rows,
}: {
  query: {
    data: T | undefined;
    error: unknown;
    isLoading: boolean;
    isError: boolean;
    refetch: () => unknown;
    dataUpdatedAt?: number;
  };
  children: (data: T) => ReactNode;
  empty?: ReactNode;
  isEmpty?: (data: T) => boolean;
  rows?: number;
}) {
  if (query.isLoading) return <Skeleton rows={rows ?? 3} />;
  if (query.data === undefined)
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  return (
    <>
      {query.isError && (
        <AlertBox
          tone="warn"
          title="Showing last known data."
          actions={
            <Button size="sm" onClick={() => void query.refetch()}>
              Retry
            </Button>
          }
        >
          {asApiError(query.error).userMessage}
          {query.dataUpdatedAt ? ` Last updated ${new Date(query.dataUpdatedAt).toLocaleTimeString()}.` : ""}
        </AlertBox>
      )}
      {isEmpty && isEmpty(query.data)
        ? (empty ?? <EmptyState title="Nothing to show" />)
        : children(query.data)}
    </>
  );
}
