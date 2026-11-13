/**
 * Leases with TTL and per-resource fences (spec/bhms/07-leases-and-authority.md §7.2-7.3).
 *
 * - `acquire` is all-or-nothing and never holds a subset while it waits (BHMS-LSE-001); a conflict that outlasts `waitMs`
 *   is `LEASE_CONFLICT` naming the conflicting resources in `bound` and when the blocking lease expires in the hint,
 *   never the holder (BHMS-LSE-002).
 * - Every grant takes the next value of the server-wide fence counter, committed with fsync before the lease exists, so
 *   fences strictly increase across restarts; `renew` keeps the fence (BHMS-LSE-003).
 * - TTL and waits are range-checked (`OUT_OF_RANGE`) and unknown resources are `INVALID_ARGUMENT` at `resources[i]`
 *   (BHMS-LSE-004). A lease belongs to its principal (BHMS-LSE-005). Expiry runs on the monotonic clock with one timer per
 *   lease plus a lazy check on every use (BHMS-LSE-006). Unknown ids read as expired (BHMS-LSE-007).
 * - {@link LeaseManager.check} is the admission and pre-dispatch check of BHMS-LSE-010 with its exact codes.
 * - {@link LeaseManager.revokeCovering} (stop) revokes active leases and raises the fence of their resources so a
 *   superseded holder is `FENCED`.
 *
 * Leases are not persisted: after a restart every earlier lease id is unknown (`LEASE_EXPIRED`), while the fence counter
 * continues. `onEnd(lease, reason)` lets the server apply `onLeaseLoss` to running operations (BHMS-LSE-012).
 *
 * Thread-safety: single event loop.
 */
import { BhmsError } from "../errors.js";
import type { Lease as WireLease } from "../generated/types.js";
import { StoreError, type Store } from "./store.js";
import { iso, mono, newId } from "./time.js";

export type LeaseState = "active" | "released" | "expired" | "revoked";

export interface Lease {
  leaseId: string;
  principal: string;
  resources: string[];
  fence: number;
  state: LeaseState;
  acquiredMs: number;
  ttlMs: number;
  expiresMono: number;
  expiresMs: number;
  timer?: NodeJS.Timeout;
}

export interface LeaseConfig {
  minTtlMs: number;
  maxTtlMs: number;
  maxWaitMs: number;
}

export function leaseWire(l: Lease): WireLease {
  return { leaseId: l.leaseId, resources: [...l.resources], fence: l.fence, state: l.state, acquiredAt: iso(l.acquiredMs), expiresAt: iso(l.expiresMs), ttlMs: l.ttlMs };
}

export class LeaseManager {
  private readonly leases = new Map<string, Lease>();
  private readonly resourceFence = new Map<string, number>();
  private waiters = new Set<() => void>();

  constructor(
    private readonly store: Store,
    private readonly cfg: LeaseConfig,
    private readonly knownResources: () => ReadonlySet<string>,
    private fenceCounter: number,
    private readonly onEnd: (lease: Lease, reason: "expired" | "revoked") => void,
  ) {}

  get fence(): number { return this.fenceCounter; }

  private nextFence(): number {
    const n = this.fenceCounter + 1;
    try {
      this.store.writeFence(n); // durable before use (BHMS-LSE-003)
    } catch (e) {
      if (e instanceof StoreError) {
        throw new BhmsError("BUSY", "the journal cannot be written, so no fence can be issued", { retry: "same-key", hint: "retry later; stop remains available" });
      }
      throw e;
    }
    this.fenceCounter = n;
    return n;
  }

  private wake(): void {
    const w = this.waiters;
    this.waiters = new Set();
    for (const f of w) f();
  }

  private expire(l: Lease): void {
    if (l.state !== "active") return;
    l.state = "expired";
    if (l.timer) clearTimeout(l.timer);
    this.onEnd(l, "expired");
    this.wake();
  }

  /** Lazy expiry check (BHMS-LSE-006). */
  private refresh(l: Lease): Lease {
    if (l.state === "active" && mono() >= l.expiresMono) this.expire(l);
    return l;
  }

  private arm(l: Lease): void {
    if (l.timer) clearTimeout(l.timer);
    l.timer = setTimeout(() => { this.expire(l); }, Math.max(0, l.expiresMono - mono()) + 1);
    l.timer.unref();
  }

  private conflicts(resources: readonly string[]): Lease[] {
    const set = new Set(resources);
    return [...this.leases.values()].filter((l) => this.refresh(l).state === "active" && l.resources.some((r) => set.has(r)));
  }

  async acquire(principal: string, resources: readonly string[], ttlMs: number, waitMs: number | undefined, signal?: AbortSignal): Promise<Lease> {
    const known = this.knownResources();
    resources.forEach((r, i) => {
      if (!known.has(r)) throw new BhmsError("INVALID_ARGUMENT", `unknown resource ${JSON.stringify(r)}`, { field: `resources[${i}]`, hint: "use resource ids from devices/describe" });
    });
    if (ttlMs < this.cfg.minTtlMs || ttlMs > this.cfg.maxTtlMs) {
      throw new BhmsError("OUT_OF_RANGE", `ttlMs ${ttlMs} is outside [${this.cfg.minTtlMs}, ${this.cfg.maxTtlMs}]`, { field: "ttlMs", bound: { minimum: this.cfg.minTtlMs, maximum: this.cfg.maxTtlMs }, hint: `ask for a ttlMs between ${this.cfg.minTtlMs} and ${this.cfg.maxTtlMs}` });
    }
    const wait = waitMs ?? 0;
    if (wait > this.cfg.maxWaitMs) {
      throw new BhmsError("OUT_OF_RANGE", `waitMs ${wait} is above the maximum ${this.cfg.maxWaitMs}`, { field: "waitMs", bound: { maximum: this.cfg.maxWaitMs }, hint: `use waitMs of at most ${this.cfg.maxWaitMs}` });
    }
    const unique = [...new Set(resources)].sort();
    const deadline = mono() + wait;
    for (;;) {
      const blocking = this.conflicts(unique);
      if (blocking.length === 0) break;
      const remaining = deadline - mono();
      if (remaining <= 0 || signal?.aborted) {
        const bound = [...new Set(blocking.flatMap((l) => l.resources).filter((r) => unique.includes(r)))].sort();
        const soonest = Math.min(...blocking.map((l) => l.expiresMono));
        throw new BhmsError("LEASE_CONFLICT", `resources ${bound.join(", ")} are leased`, {
          field: "resources", bound, hint: `the blocking lease expires in about ${Math.max(0, Math.ceil(soonest - mono()))} ms; retry then, or pass waitMs`,
        });
      }
      await new Promise<void>((resolve) => {
        const t = setTimeout(done, remaining);
        const self = this;
        function done(): void {
          clearTimeout(t);
          self.waiters.delete(done);
          signal?.removeEventListener("abort", done);
          resolve();
        }
        this.waiters.add(done);
        signal?.addEventListener("abort", done, { once: true });
      });
    }
    const fence = this.nextFence();
    const now = Date.now();
    const lease: Lease = {
      leaseId: newId("lease"), principal, resources: unique, fence, state: "active", acquiredMs: now, ttlMs,
      expiresMono: mono() + ttlMs, expiresMs: now + ttlMs,
    };
    for (const r of unique) this.resourceFence.set(r, Math.max(this.resourceFence.get(r) ?? 0, fence));
    this.leases.set(lease.leaseId, lease);
    this.arm(lease);
    return lease;
  }

  private mine(principal: string, leaseId: string): Lease {
    const l = this.leases.get(leaseId);
    if (!l) throw new BhmsError("LEASE_EXPIRED", `lease ${leaseId} is unknown or ended`, { field: "leaseId", hint: "acquire a new lease" });
    if (l.principal !== principal) throw new BhmsError("LEASE_CONFLICT", "that lease is not yours", { field: "leaseId", hint: "acquire your own lease" });
    return this.refresh(l);
  }

  renew(principal: string, leaseId: string, ttlMs: number): Lease {
    const l = this.mine(principal, leaseId);
    if (ttlMs < this.cfg.minTtlMs || ttlMs > this.cfg.maxTtlMs) {
      throw new BhmsError("OUT_OF_RANGE", `ttlMs ${ttlMs} is outside [${this.cfg.minTtlMs}, ${this.cfg.maxTtlMs}]`, { field: "ttlMs", bound: { minimum: this.cfg.minTtlMs, maximum: this.cfg.maxTtlMs }, hint: `ask for a ttlMs between ${this.cfg.minTtlMs} and ${this.cfg.maxTtlMs}` });
    }
    if (l.state === "revoked") throw new BhmsError("FENCED", `lease ${leaseId} was revoked`, { field: "leaseId", hint: "acquire a new lease" });
    if (l.state !== "active") throw new BhmsError("LEASE_EXPIRED", `lease ${leaseId} is ${l.state}`, { field: "leaseId", hint: "acquire a new lease" });
    l.ttlMs = ttlMs;
    l.expiresMono = mono() + ttlMs;
    l.expiresMs = Date.now() + ttlMs;
    this.arm(l);
    return l;
  }

  release(principal: string, leaseId: string): Lease {
    const l = this.mine(principal, leaseId);
    if (l.state !== "active") return l; // BHMS-LSE-006: unchanged
    l.state = "released";
    if (l.timer) clearTimeout(l.timer);
    this.wake();
    return l;
  }

  /** The admission and pre-dispatch lease check of BHMS-LSE-010; returns the lease when it is good. */
  check(principal: string, leaseId: string | undefined, resources: readonly string[]): Lease {
    if (leaseId === undefined) {
      throw new BhmsError("LEASE_REQUIRED", "this action needs a lease", { field: "leaseId", bound: [...resources], hint: `acquire a lease covering ${resources.join(", ")} with leases/acquire and pass its leaseId` });
    }
    const l = this.leases.get(leaseId);
    if (!l) throw new BhmsError("LEASE_EXPIRED", `lease ${leaseId} is unknown or ended`, { field: "leaseId", hint: "acquire a new lease" });
    if (l.principal !== principal) throw new BhmsError("LEASE_CONFLICT", "that lease is not yours", { field: "leaseId", hint: "acquire your own lease" });
    this.refresh(l);
    if (l.state === "expired" || l.state === "released") throw new BhmsError("LEASE_EXPIRED", `lease ${leaseId} is ${l.state}`, { field: "leaseId", hint: "acquire a new lease" });
    if (l.state === "revoked") throw new BhmsError("FENCED", `lease ${leaseId} was revoked`, { field: "leaseId", hint: "acquire a new lease" });
    const missing = resources.filter((r) => !l.resources.includes(r));
    if (missing.length > 0) {
      throw new BhmsError("LEASE_CONFLICT", `lease ${leaseId} does not cover ${missing.join(", ")}`, { field: "leaseId", bound: [...resources], hint: `acquire a lease covering ${resources.join(", ")}` });
    }
    const highest = Math.max(0, ...resources.map((r) => this.resourceFence.get(r) ?? 0));
    if (l.fence < highest) throw new BhmsError("FENCED", `lease ${leaseId} has fence ${l.fence}, below the resource fence ${highest}`, { field: "leaseId", hint: "acquire a new lease" });
    return l;
  }

  /** Whether `principal` holds an active lease covering every resource (authorizes a transaction read, BHMS-OBS-011). */
  holds(principal: string, resources: readonly string[]): boolean {
    return [...this.leases.values()].some((l) => l.principal === principal && this.refresh(l).state === "active" && resources.every((r) => l.resources.includes(r)));
  }

  /** The lease with this id, refreshed (undefined when unknown). */
  get(leaseId: string): Lease | undefined {
    const l = this.leases.get(leaseId);
    return l ? this.refresh(l) : undefined;
  }

  /** Revoke every active lease covering one of `resources`; raises their fence. Returns the revoked leases (BHMS-AUTH-021). */
  revokeCovering(resources: readonly string[]): Lease[] {
    const hit = this.conflicts(resources);
    let fence: number;
    try {
      fence = this.nextFence();
    } catch {
      fence = ++this.fenceCounter; // degraded audit: revoke anyway, stop is never blocked (BHMS-AUTH-025)
    }
    for (const r of resources) this.resourceFence.set(r, Math.max(this.resourceFence.get(r) ?? 0, fence));
    for (const l of hit) {
      l.state = "revoked";
      if (l.timer) clearTimeout(l.timer);
      this.onEnd(l, "revoked");
    }
    this.wake();
    return hit;
  }

  close(): void {
    for (const l of this.leases.values()) if (l.timer) clearTimeout(l.timer);
    this.wake();
  }
}
