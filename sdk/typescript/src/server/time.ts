/** Time helpers shared by the server runtime. Wall-clock times are for display; durations use the monotonic clock. */
import { randomBytes } from "node:crypto";
import { performance } from "node:perf_hooks";

/** ISO-8601 UTC with millisecond precision (`2026-11-13T09:30:05.004Z`). */
export function iso(ms: number): string {
  return new Date(ms).toISOString();
}

/** Milliseconds on the monotonic clock (never steps backwards; BHMS-LSE-006, BHMS-OBS-003). */
export function mono(): number {
  return performance.now();
}

/** A server-minted identifier (BHMS-LIF-031): time-ordered and unguessable. */
export function newId(prefix: string): string {
  return `${prefix}-${Date.now().toString(16)}${randomBytes(5).toString("hex")}`;
}

export const sleep = (ms: number, signal?: AbortSignal): Promise<void> =>
  new Promise((resolve) => {
    if (signal?.aborted) { resolve(); return; }
    const t = setTimeout(done, ms);
    function done(): void {
      clearTimeout(t);
      signal?.removeEventListener("abort", done);
      resolve();
    }
    signal?.addEventListener("abort", done, { once: true });
  });
