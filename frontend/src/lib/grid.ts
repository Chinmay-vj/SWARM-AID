/**
 * Local simulator grid geometry (crs "swarm-aid:grid", unit: cell). These are NOT geographic
 * coordinates. Cell (x, y) covers [x, x+1) × [y, y+1); a reported point at integer (x, y)
 * refers to the centre of that cell.
 */
import type { Location } from "../contracts/api";

export const LOCAL_CRS = "swarm-aid:grid";

export interface View {
  scale: number; // screen pixels per cell
  tx: number; // screen offset in pixels
  ty: number;
}

export function cellCenter(x: number, y: number, cellPx: number): [number, number] {
  return [(x + 0.5) * cellPx, (y + 0.5) * cellPx];
}

/** World (cell) to screen (pixel) for the current pan/zoom view. */
export function toScreen(view: View, x: number, y: number): [number, number] {
  return [(x + 0.5) * view.scale + view.tx, (y + 0.5) * view.scale + view.ty];
}

/** Screen pixel to fractional cell coordinate. */
export function toCell(view: View, sx: number, sy: number): [number, number] {
  return [(sx - view.tx) / view.scale - 0.5, (sy - view.ty) / view.scale - 0.5];
}

/** View that fits a width×height grid inside a viewport with padding, centred. */
export function fitView(width: number, height: number, viewportW: number, viewportH: number, pad = 16): View {
  const scale = Math.max(4, Math.min((viewportW - pad * 2) / width, (viewportH - pad * 2) / height));
  return { scale, tx: (viewportW - width * scale) / 2, ty: (viewportH - height * scale) / 2 };
}

/** Zoom around a screen anchor point, clamped. */
export function zoomAt(view: View, factor: number, ax: number, ay: number, min = 4, max = 200): View {
  const scale = Math.min(max, Math.max(min, view.scale * factor));
  const k = scale / view.scale;
  return { scale, tx: ax - (ax - view.tx) * k, ty: ay - (ay - view.ty) * k };
}

/**
 * Accept a location for drawing on the local grid. Rejects missing, non-local or out-of-bounds
 * coordinates instead of drawing them at a wrong place (e.g. never at (0,0) by default).
 */
export function drawable(loc: Location | null | undefined, width: number, height: number): loc is Location {
  if (!loc || loc.crs !== LOCAL_CRS) return false;
  if (!Number.isFinite(loc.x) || !Number.isFinite(loc.y)) return false;
  return loc.x >= 0 && loc.y >= 0 && loc.x < width && loc.y < height;
}
