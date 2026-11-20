/**
 * `subscriptions/listen` (spec/bhms/03-lifecycle.md §3.7, 05 §5.3, 09 §9.4).
 *
 * {@link listen} is an async generator the session turns into a response stream: it yields the acknowledgement first
 * (BHMS-LIF-040: the honoured subset of the filter, and a `refused` entry for every part it will not honour), then only
 * the notification types the client asked for (BHMS-LIF-041), and finally a `Complete` with an `endReason` when the
 * *server* ends the subscription (BHMS-LIF-044): `shutdown` when the server closes, `overflow` when the client did not keep
 * up, `unauthorized` when its `read` scope was revoked (authorization is re-evaluated at every delivery, BHMS-LIF-042).
 * When the client cancels or disconnects the generator is simply closed and sends nothing more (BHMS-LIF-051).
 *
 * The per-subscription queue is bounded (1024). On overflow the oldest observation notifications are dropped first;
 * notifications for terminal operation states are never dropped, and if the queue is full of undroppable items the
 * subscription ends with `overflow` rather than blocking device work (BHMS-LIF-043).
 *
 * Events: with `events.after` the retained events after that cursor are delivered first, then live events, with no
 * duplicate and no omission between the two (BHMS-EVT-020): the replay is read and the live listener installed in the
 * same synchronous step. A cursor older than the retained log sets `eventsGap` on the acknowledgement.
 *
 * Thread-safety: single event loop.
 */
import { BhmsError } from "../errors.js";
import type { Event, Operation, RefusedFilter, SubscriptionFilter } from "../generated/types.js";
import { Complete, type Notification, type Peer } from "../jsonrpc/session.js";
import type { Principal } from "./authority.js";
import type { DeviceServer } from "./server.js";
import type { ChangeKind, OperationRecord } from "./operations.js";

const MAX_QUEUE = 1024;

interface Item {
  note: Notification;
  droppable: boolean;
}

export async function* listen(
  srv: DeviceServer,
  principal: Principal,
  peer: Peer,
  filter: SubscriptionFilter,
  signal: AbortSignal,
  authenticate: () => Principal = () => srv.policy(peer),
): AsyncGenerator<Notification | Complete> {
  const refused: RefusedFilter[] = [];
  const honoured: SubscriptionFilter = {};
  const queue: Item[] = [];
  const cleanups: Array<() => void> = [];
  let wake: (() => void) | undefined;
  let end: "overflow" | "shutdown" | "unauthorized" | undefined;
  const poke = (): void => { const w = wake; wake = undefined; w?.(); };
  const push = (item: Item): void => {
    if (end) return;
    if (queue.length >= MAX_QUEUE) {
      const i = queue.findIndex((q) => q.droppable);
      if (i < 0) { end = "overflow"; poke(); return; }
      queue.splice(i, 1);
    }
    queue.push(item);
    poke();
  };
  const refuse = (path: string, code: ConstructorParameters<typeof BhmsError>[0], hint: string): void => { refused.push({ path, bhmsCode: code, hint }); };

  const canSee = (rec: OperationRecord): boolean => rec.principal === principal.id || principal.operationsAll;

  if (!principal.canRead) {
    for (const k of Object.keys(filter)) refuse(k, "UNAUTHORIZED", "subscriptions need the read scope (missing scope read)");
  } else {
    // devices list
    if (filter.devicesListChanged === true) {
      honoured.devicesListChanged = true;
      const l = (): void => push({ note: { method: "notifications/devices/listChanged", params: {} }, droppable: false });
      srv.deviceListeners.add(l);
      cleanups.push(() => srv.deviceListeners.delete(l));
    } else if (filter.devicesListChanged === false) {
      /* explicitly not wanted */
    }

    // operations
    const ops = filter.operations;
    if (ops) {
      const okIds: string[] = [];
      (ops.operationIds ?? []).forEach((id, i) => {
        const rec = srv.journal.get(id);
        if (!rec || !canSee(rec)) refuse(`operations.operationIds[${i}]`, "INVALID_ARGUMENT", "use an operationId returned to you");
        else okIds.push(id);
      });
      const deviceIds: string[] = [];
      (ops.deviceIds ?? []).forEach((d, i) => {
        if (!srv.devices.has(d)) refuse(`operations.deviceIds[${i}]`, "UNKNOWN_DEVICE", "devices/list shows the devices you can use");
        else deviceIds.push(d);
      });
      honoured.operations = {
        ...(ops.operationIds !== undefined ? { operationIds: okIds } : {}),
        ...(ops.deviceIds !== undefined ? { deviceIds } : {}),
        ...(ops.all !== undefined ? { all: ops.all } : {}),
      };
      const l = (rec: OperationRecord, _changed: ChangeKind[], wire?: Operation): void => {
        if (!canSee(rec)) return;
        const match = ops.all === true || okIds.includes(rec.id) || (rec.op.deviceId !== undefined && deviceIds.includes(rec.op.deviceId));
        if (!match) return;
        push({ note: { method: "notifications/operation", params: { operation: wire ?? rec.wire() } }, droppable: false });
      };
      srv.journal.listeners.add(l);
      cleanups.push(() => srv.journal.listeners.delete(l));
    }

    // observations
    if (filter.observations) {
      const accepted: NonNullable<SubscriptionFilter["observations"]> = [];
      filter.observations.forEach((o, i) => {
        const dev = srv.devices.get(o.deviceId);
        if (!dev) { refuse(`observations[${i}]`, "UNKNOWN_DEVICE", "devices/list shows the devices you can use"); return; }
        const spec = dev.properties.get(o.property);
        if (!spec) { refuse(`observations[${i}]`, "INVALID_ARGUMENT", `the properties are: ${[...dev.properties.keys()].sort().join(", ")}`); return; }
        if (!spec.observable) { refuse(`observations[${i}]`, "UNSUPPORTED", `${o.property} is not observable; read it with properties/read`); return; }
        if (spec.readEffect === "transaction" && !principal.canInvoke(dev.deviceId, spec.name, dev.capabilities)) {
          refuse(`observations[${i}]`, "UNAUTHORIZED", `a subscription would start device transactions; missing scope invoke:${dev.deviceId}/${spec.name} (BHMS-OBS-022)`);
          return;
        }
        accepted.push(o);
        const off = srv.observations.subscribe(dev, o.property, o.minIntervalMs, (n) => {
          push({ note: { method: "notifications/observation", params: { deviceId: n.deviceId, property: n.property, observation: n.observation } }, droppable: true });
        });
        cleanups.push(off);
      });
      honoured.observations = accepted;
    }
  }

  // events: replay first, then live, in one synchronous step (BHMS-EVT-020)
  let eventsGap = false;
  const evf = filter.events;
  if (evf && principal.canRead) {
    honoured.events = { ...evf };
    const wanted = (e: Event): boolean => (!evf.deviceIds || evf.deviceIds.length === 0 || (e.deviceId !== undefined && evf.deviceIds.includes(e.deviceId))) && (!evf.types || evf.types.length === 0 || evf.types.includes(e.type));
    if (evf.after !== undefined) {
      try {
        const r = srv.events.replay(evf.after);
        eventsGap = r.gap;
        for (const e of r.events) if (wanted(e)) push({ note: { method: "notifications/event", params: { event: e } }, droppable: false });
      } catch (e) {
        if (e instanceof BhmsError) {
          refuse("events.after", e.bhmsCode, e.hint);
          delete honoured.events.after;
        } else throw e;
      }
    }
    const l = (e: Event): void => { if (wanted(e)) push({ note: { method: "notifications/event", params: { event: e } }, droppable: false }); };
    srv.events.listeners.add(l);
    cleanups.push(() => srv.events.listeners.delete(l));
  } else if (evf) {
    refuse("events", "UNAUTHORIZED", "events need the read scope (missing scope read)");
  }

  const ack: Record<string, unknown> = { notifications: honoured };
  if (refused.length > 0) ack.refused = refused;
  if (eventsGap) ack.eventsGap = true;
  try {
    yield { method: "notifications/subscriptions/acknowledged", params: ack };
    const closing = srv.closingSignal;
    for (;;) {
      if (signal.aborted) return; // the client is gone: say nothing more (BHMS-LIF-051)
      try {
        if (!authenticate().canRead) { end = "unauthorized"; queue.length = 0; }
      } catch (error) {
        if (!(error instanceof BhmsError) || error.bhmsCode !== "UNAUTHORIZED") throw error;
        end = "unauthorized"; queue.length = 0;
      }
      if (closing.aborted && !end) end = "shutdown";
      const item = queue.shift();
      if (item) { yield item.note; continue; }
      if (end) { yield new Complete({ resultType: "complete", endReason: end }); return; }
      await new Promise<void>((resolve) => {
        // re-check authority periodically even when idle, so revocation ends delivery promptly (BHMS-LIF-042)
        const timer = setTimeout(done, 1000);
        timer.unref();
        function done(): void {
          clearTimeout(timer);
          signal.removeEventListener("abort", done);
          closing.removeEventListener("abort", done);
          wake = undefined;
          resolve();
        }
        wake = done;
        signal.addEventListener("abort", done, { once: true });
        closing.addEventListener("abort", done, { once: true });
      });
    }
  } finally {
    for (const c of cleanups) c();
  }
}
