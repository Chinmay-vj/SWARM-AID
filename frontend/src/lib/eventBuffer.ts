/**
 * Per-mission ordered event buffer.
 *
 * The backend delivers at-least-once with a per-mission sequence. This buffer
 *  - drops duplicates (sequence <= last applied),
 *  - holds out-of-order events until the gap closes,
 *  - reports a gap that persists past `maxHeld` so the caller resynchronizes from
 *    GET /missions/{id}/events?after_sequence=n,
 *  - keeps a bounded history.
 */
export interface Sequenced {
  sequence: number;
}

export type OfferResult<T> =
  | { kind: "applied"; events: T[] }
  | { kind: "duplicate" }
  | { kind: "held" }
  | { kind: "gap"; after: number };

export class EventBuffer<T extends Sequenced> {
  private held = new Map<number, T>();
  private history: T[] = [];
  lastApplied: number;

  constructor(
    start = 0,
    private readonly capacity = 500,
    private readonly maxHeld = 50,
  ) {
    this.lastApplied = start;
  }

  offer(event: T): OfferResult<T> {
    if (event.sequence <= this.lastApplied || this.held.has(event.sequence)) return { kind: "duplicate" };
    if (event.sequence !== this.lastApplied + 1) {
      this.held.set(event.sequence, event);
      if (this.held.size > this.maxHeld) return { kind: "gap", after: this.lastApplied };
      return { kind: "held" };
    }
    const applied: T[] = [event];
    this.lastApplied = event.sequence;
    let next = this.held.get(this.lastApplied + 1);
    while (next) {
      this.held.delete(next.sequence);
      applied.push(next);
      this.lastApplied = next.sequence;
      next = this.held.get(this.lastApplied + 1);
    }
    this.remember(applied);
    return { kind: "applied", events: applied };
  }

  /** Apply a replayed batch (already ordered by the server). */
  replay(events: readonly T[]): T[] {
    const applied: T[] = [];
    for (const e of [...events].sort((a, b) => a.sequence - b.sequence)) {
      const r = this.offer(e);
      if (r.kind === "applied") applied.push(...r.events);
    }
    return applied;
  }

  /** Reset after a snapshot resynchronization: everything up to `sequence` is known. */
  resetTo(sequence: number): void {
    this.lastApplied = sequence;
    for (const key of [...this.held.keys()]) if (key <= sequence) this.held.delete(key);
  }

  get heldCount(): number {
    return this.held.size;
  }

  get recent(): readonly T[] {
    return this.history;
  }

  private remember(events: T[]): void {
    // Copy before reversing: the caller receives `events` in ascending order.
    this.history = [...events].reverse().concat(this.history).slice(0, this.capacity);
  }
}
