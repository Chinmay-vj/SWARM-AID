/** Tables, pagination, tabs, search and select fields. */
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Search } from "lucide-react";
import { useId, useMemo, useState, type KeyboardEvent, type ReactNode } from "react";
import { Button } from "./primitives";

export interface Column<T> {
  key: string;
  header: string;
  cell: (row: T) => ReactNode;
  sort?: (row: T) => string | number | null;
  className?: string;
}

export type SortState = { key: string; dir: "asc" | "desc" } | null;

export function sortRows<T>(rows: readonly T[], columns: readonly Column<T>[], sort: SortState): T[] {
  if (!sort) return [...rows];
  const col = columns.find((c) => c.key === sort.key);
  if (!col?.sort) return [...rows];
  const get = col.sort;
  const dir = sort.dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const va = get(a);
    const vb = get(b);
    if (va === vb) return 0;
    if (va === null) return 1; // unknown values always sort last
    if (vb === null) return -1;
    return va < vb ? -dir : dir;
  });
}

export function DataTable<T>({
  rows,
  columns,
  rowKey,
  caption,
  onSelect,
  selectedKey,
  initialSort = null,
  empty,
}: {
  rows: readonly T[];
  columns: readonly Column<T>[];
  rowKey: (row: T) => string;
  caption: string;
  onSelect?: (row: T) => void;
  selectedKey?: string | null;
  initialSort?: SortState;
  empty?: ReactNode;
}) {
  const [sort, setSort] = useState<SortState>(initialSort);
  const sorted = useMemo(() => sortRows(rows, columns, sort), [rows, columns, sort]);
  const toggle = (key: string) =>
    setSort((s) => (s?.key === key ? (s.dir === "asc" ? { key, dir: "desc" } : null) : { key, dir: "asc" }));
  const onKey = (e: KeyboardEvent, row: T) => {
    if (onSelect && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      onSelect(row);
    }
  };
  if (rows.length === 0 && empty) return <>{empty}</>;
  return (
    <div className="table-wrap">
      <table className="table">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                scope="col"
                aria-sort={
                  sort?.key === c.key ? (sort.dir === "asc" ? "ascending" : "descending") : undefined
                }
              >
                {c.sort ? (
                  <button onClick={() => toggle(c.key)}>
                    {c.header}
                    {sort?.key === c.key ? (
                      sort.dir === "asc" ? (
                        <ArrowUp size={12} aria-hidden="true" />
                      ) : (
                        <ArrowDown size={12} aria-hidden="true" />
                      )
                    ) : (
                      <ArrowUpDown size={12} aria-hidden="true" opacity={0.5} />
                    )}
                  </button>
                ) : (
                  c.header
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => {
            const k = rowKey(row);
            return (
              <tr
                key={k}
                className={`${onSelect ? "selectable" : ""} ${selectedKey === k ? "selected" : ""}`}
                onClick={onSelect ? () => onSelect(row) : undefined}
                onKeyDown={onSelect ? (e) => onKey(e, row) : undefined}
                tabIndex={onSelect ? 0 : undefined}
                aria-selected={onSelect ? selectedKey === k : undefined}
              >
                {columns.map((c) => (
                  <td key={c.key} className={c.className}>
                    {c.cell(row)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function Pagination({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}) {
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.max(1, Math.ceil(total / limit));
  return (
    <nav className="pagination" aria-label="Pagination">
      <span className="muted">
        {total === 0 ? "0 results" : `${offset + 1}–${Math.min(total, offset + limit)} of ${total}`}
      </span>
      <Button
        size="sm"
        aria-label="Previous page"
        disabled={page <= 1}
        onClick={() => onChange(Math.max(0, offset - limit))}
        icon={<ChevronLeft size={14} aria-hidden="true" />}
      />
      <span aria-live="polite">
        Page {page} / {pages}
      </span>
      <Button
        size="sm"
        aria-label="Next page"
        disabled={page >= pages}
        onClick={() => onChange(offset + limit)}
        icon={<ChevronRight size={14} aria-hidden="true" />}
      />
    </nav>
  );
}

export function SelectField({
  label,
  value,
  onChange,
  options,
  help,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: (string | { value: string; label: string })[];
  help?: string;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) =>
          typeof o === "string" ? (
            <option key={o} value={o}>
              {o || "All"}
            </option>
          ) : (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ),
        )}
      </select>
      {help && <span className="help">{help}</span>}
    </div>
  );
}

export function SearchField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="row" style={{ gap: 4, flexWrap: "nowrap" }}>
        <Search size={14} aria-hidden="true" className="muted" />
        <input
          id={id}
          type="search"
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
    </div>
  );
}

export function TextField({
  label,
  value,
  onChange,
  type = "text",
  required,
  help,
  error,
  autoComplete,
  min,
  max,
  maxLength,
  multiline,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  required?: boolean;
  help?: string;
  error?: string | null;
  autoComplete?: string;
  min?: number;
  max?: number;
  maxLength?: number;
  multiline?: boolean;
}) {
  const id = useId();
  const describedBy =
    [help ? `${id}-help` : "", error ? `${id}-err` : ""].filter(Boolean).join(" ") || undefined;
  return (
    <div className="field">
      <label htmlFor={id}>
        {label}
        {required ? " *" : ""}
      </label>
      {multiline ? (
        <textarea
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required={required}
          aria-invalid={Boolean(error)}
          aria-describedby={describedBy}
          maxLength={maxLength}
        />
      ) : (
        <input
          id={id}
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required={required}
          aria-invalid={Boolean(error)}
          aria-describedby={describedBy}
          autoComplete={autoComplete}
          min={min}
          max={max}
          maxLength={maxLength}
        />
      )}
      {help && (
        <span className="help" id={`${id}-help`}>
          {help}
        </span>
      )}
      {error && (
        <span className="error" id={`${id}-err`} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}

export function Tabs<K extends string>({
  tabs,
  active,
  onChange,
  label,
}: {
  tabs: { key: K; label: string }[];
  active: K;
  onChange: (k: K) => void;
  label: string;
}) {
  const base = useId();
  const onKey = (e: KeyboardEvent, i: number) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length]!;
    onChange(next.key);
    document.getElementById(`${base}-${next.key}`)?.focus();
  };
  return (
    <div className="tabs">
      <div role="tablist" aria-label={label}>
        {tabs.map((t, i) => (
          <button
            key={t.key}
            id={`${base}-${t.key}`}
            role="tab"
            aria-selected={active === t.key}
            tabIndex={active === t.key ? 0 : -1}
            onClick={() => onChange(t.key)}
            onKeyDown={(e) => onKey(e, i)}
          >
            {t.label}
          </button>
        ))}
      </div>
    </div>
  );
}
