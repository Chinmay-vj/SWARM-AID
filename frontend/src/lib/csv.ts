/**
 * CSV helpers for client-side exports (synthetic exports and table downloads).
 * Cells beginning with = + - @ tab or carriage return are prefixed with an apostrophe so
 * spreadsheet applications do not evaluate them as formulas (CSV/formula injection).
 */
const FORMULA_START = /^[=+\-@\t\r]/;

export function escapeCsvCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  let text = typeof value === "object" ? JSON.stringify(value) : String(value);
  if (FORMULA_START.test(text) && !/^-?\d+(\.\d+)?(e[+-]?\d+)?$/i.test(text)) text = `'${text}`;
  if (/[",\n\r]/.test(text)) text = `"${text.replace(/"/g, '""')}"`;
  return text;
}

export function toCsv(header: readonly string[], rows: readonly (readonly unknown[])[]): string {
  return [header, ...rows].map((row) => row.map(escapeCsvCell).join(",")).join("\r\n") + "\r\n";
}

/**
 * Backend CSV exports are generated server-side by Python's csv module, which does not
 * neutralise formulas. Re-encode each cell before saving so downloaded files are safe to open.
 */
export function sanitizeCsvText(csv: string): string {
  return toCsv(...splitCsv(csv));
}

function splitCsv(csv: string): [string[], string[][]] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < csv.length; i++) {
    const ch = csv[i]!;
    if (quoted) {
      if (ch === '"' && csv[i + 1] === '"') {
        cell += '"';
        i++;
      } else if (ch === '"') quoted = false;
      else cell += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") {
      row.push(cell);
      cell = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && csv[i + 1] === "\n") i++;
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else cell += ch;
  }
  if (cell !== "" || row.length) {
    row.push(cell);
    rows.push(row);
  }
  const [header = [], ...body] = rows;
  return [header, body];
}

/** Trigger a browser download of text content without navigating. */
export function downloadText(filename: string, content: string, mediaType: string): void {
  const blob = new Blob([content], { type: mediaType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
