/**
 * The cursor-addressed event log (spec/bhms/09-events-and-streams.md).
 *
 * Cursors are `ev-NNNNNN` (opaque to clients, BHMS-EVT-001), totally ordered; the counter continues across restarts of a
 * durable server (it is recovered from the journal). `read()` returns events strictly after `after` in cursor order
 * (BHMS-EVT-010) and sets `gap` when `after` is older than the oldest retained event or newer than the log's head, i.e.
 * the log was reset (BHMS-EVT-011). Events are retained for `retentionS` seconds (BHMS-EVT-012).
 *
 * Thread-safety: single event loop.
 */
import { BhmsError } from "../errors.js";
import type { Event } from "../generated/types.js";
import { iso } from "./time.js";
import type { Store } from "./store.js";

const CURSOR = /^ev-(\d{6,12})$/;

export interface NewEvent {
  severity?: Event["severity"];
  deviceId?: string;
  operationId?: string;
  message?: string;
  data?: Record<string, unknown>;
}

export class EventLog {
  private events: Event[] = [];
  private counter = 0;
  private sincePrune = 0;
  /** Listeners called synchronously after every append (live subscriptions). */
  readonly listeners = new Set<(ev: Event) => void>();

  constructor(private readonly store: Store, readonly retentionS: number, loaded: Event[]) {
    this.events = loaded;
    for (const e of loaded) this.counter = Math.max(this.counter, Number(CURSOR.exec(e.cursor)?.[1] ?? 0));
  }

  static cursorOf(n: number): string {
    return `ev-${String(n).padStart(6, "0")}`;
  }

  get head(): string { return EventLog.cursorOf(this.counter); }

  append(type: string, o: NewEvent = {}): Event {
    const ev: Event = { cursor: EventLog.cursorOf(++this.counter), time: iso(Date.now()), type, severity: o.severity ?? "info" };
    if (o.deviceId !== undefined) ev.deviceId = o.deviceId;
    if (o.operationId !== undefined) ev.operationId = o.operationId;
    if (o.message !== undefined) ev.message = o.message.slice(0, 1000);
    if (o.data !== undefined) ev.data = o.data;
    this.events.push(ev);
    this.store.writeEvent(ev);
    if (++this.sincePrune >= 256) this.prune(Date.now()); // bounded memory and journal even on a long-running server
    for (const l of [...this.listeners]) {
      try { l(ev); } catch { /* a listener must not break event recording */ }
    }
    return ev;
  }

  private position(after: string, field: string): number {
    const m = CURSOR.exec(after);
    if (!m) throw new BhmsError("INVALID_ARGUMENT", `${field} ${JSON.stringify(after)} is not a cursor of this server`, { field, hint: "pass a cursor returned by events/read or an event's cursor" });
    return Number(m[1]);
  }

  /** Events strictly after `after`, optionally filtered; `gap` per BHMS-EVT-011. */
  read(o: { after?: string; limit: number; deviceId?: string; types?: readonly string[]; field?: string }): { events: Event[]; cursor: string; gap: boolean } {
    let gap = false;
    let start = 0;
    if (o.after !== undefined) {
      const n = this.position(o.after, o.field ?? "after");
      const oldest = this.events.length > 0 ? this.position(this.events[0].cursor, "after") : this.counter + 1;
      if (n > this.counter) gap = true; // the log was reset: the client's cursor is from another life
      else if (n + 1 < oldest) gap = true;
      start = n > this.counter ? 0 : n;
    }
    const out: Event[] = [];
    let last = o.after !== undefined && !gap ? o.after : undefined;
    for (const ev of this.events) {
      const n = Number(CURSOR.exec(ev.cursor)![1]);
      if (n <= start) continue;
      if ((o.deviceId !== undefined && ev.deviceId !== o.deviceId) || (o.types && o.types.length > 0 && !o.types.includes(ev.type))) {
        last = ev.cursor;
        continue;
      }
      if (out.length >= o.limit) break;
      out.push(ev);
      last = ev.cursor;
    }
    return { events: out, cursor: out.length > 0 ? out[out.length - 1].cursor : (last ?? this.head), gap };
  }

  /** Events after `after` for a live subscription's replay, plus whether the cursor was too old (BHMS-EVT-020). */
  replay(after: string): { events: Event[]; gap: boolean } {
    const r = this.read({ after, limit: Number.MAX_SAFE_INTEGER });
    return { events: r.events, gap: r.gap };
  }

  prune(nowMs: number): void {
    const cutoff = nowMs - this.retentionS * 1000;
    this.sincePrune = 0;
    this.events = this.events.filter((e) => Date.parse(e.time) >= cutoff);
    this.store.pruneEvents(cutoff);
  }
}
