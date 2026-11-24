export { formatLocation, formatSimTime } from "../../lib/format";
import { statusLabel } from "../../lib/status";

export function statusLabelSafe(v: string | null): string {
  return v ? statusLabel(v) : "not reported";
}
