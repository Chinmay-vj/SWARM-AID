/** Small presentational primitives: buttons, badges, panels, key/value lists, metrics. */
import { useId, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { TONE_GLYPH, statusLabel, toneFor, type Tone } from "../../lib/status";

type ButtonVariant = "default" | "primary" | "ok" | "bad" | "warn" | "ghost";

export function Button({
  variant = "default",
  size,
  icon,
  children,
  className = "",
  type = "button",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: "sm"; icon?: ReactNode }) {
  const cls = [
    "btn",
    variant !== "default" ? variant : "",
    size ?? "",
    !children ? "icon-btn" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <button type={type} className={cls} {...rest}>
      {icon}
      {children}
    </button>
  );
}

/** Status badge: colour + glyph + text, so status never depends on colour alone. */
export function StatusBadge({
  status,
  tone,
  label,
  title,
}: {
  status: string | null | undefined;
  tone?: Tone;
  label?: string;
  title?: string;
}) {
  const t = tone ?? toneFor(status);
  return (
    <span className={`badge tone-${t}`} title={title}>
      <span className="glyph" aria-hidden="true">
        {TONE_GLYPH[t]}
      </span>
      {label ?? statusLabel(status)}
    </span>
  );
}

export function SourceTag({ synthetic, measured = false }: { synthetic: boolean; measured?: boolean }) {
  if (synthetic)
    return (
      <span className="source-tag" title="Synthetic demonstration data, not measured results">
        Synthetic
      </span>
    );
  return measured ? (
    <span className="source-tag measured" title="Measured by the backend from simulation outputs">
      Measured
    </span>
  ) : null;
}

export function Panel({
  title,
  actions,
  children,
  className = "",
  id,
  labelledBy,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
  labelledBy?: string;
}) {
  const generated = useId();
  const headingId = id ? `${id}-title` : generated;
  return (
    <section className={`panel ${className}`} aria-labelledby={title ? headingId : labelledBy} id={id}>
      {(title || actions) && (
        <div className="panel-head">
          {title && <h2 id={headingId}>{title}</h2>}
          {actions && <div className="row">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Kv({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="kv">
      {items.map(([k, v], i) => (
        <div key={i} style={{ display: "contents" }}>
          <dt>{k}</dt>
          <dd>{v ?? <span className="muted">unknown</span>}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Metric({
  label,
  value,
  hint,
  tone = "accent",
  to,
  synthetic,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: Tone | "accent";
  to?: string;
  synthetic?: boolean;
}) {
  const color = {
    ok: "var(--ok)",
    warn: "var(--warn)",
    bad: "var(--bad)",
    info: "var(--info)",
    muted: "var(--unknown)",
    accent: "var(--accent)",
  }[tone];
  const body = (
    <>
      <span className="label">{label}</span>
      <span className="value">{value}</span>
      <span className="hint">
        {hint}
        {synthetic ? " · synthetic" : ""}
      </span>
    </>
  );
  const style = { ["--tone" as string]: color };
  return to ? (
    <Link className="metric" to={to} style={style}>
      {body}
    </Link>
  ) : (
    <div className="metric" style={style}>
      {body}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="row">{actions}</div>}
    </div>
  );
}

export function Bar({ fraction, label }: { fraction: number | null; label: string }) {
  if (fraction === null) return <span className="muted small">unknown</span>;
  const pct = Math.round(Math.max(0, Math.min(1, fraction)) * 100);
  const color = pct < 25 ? "var(--bad)" : pct < 50 ? "var(--warn)" : "var(--ok)";
  return (
    <div className="row" style={{ gap: 6 }}>
      <div
        className="bar grow"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-label={label}
      >
        <i style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="xs nowrap">{pct}%</span>
    </div>
  );
}
