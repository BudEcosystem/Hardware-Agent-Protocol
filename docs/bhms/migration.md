# Migrating to this release (BHMS Python SDK)

Four changes of the hardening round (spec/bhms/CHANGELOG.md, "Unreleased") can break code that worked before. Each
entry says what you will see and what to change.

## 1. The holder of a lease must present it (BHMS-LSE-014)

While a lease is active on a resource, every action that uses that resource is refused unless the request presents that
lease. This holds for actions that do not declare `requiresLease`, and for the principal that holds the lease.

- You will see: `LEASE_CONFLICT`, `field: "leaseId"`, `bound` listing the leased resources, message "... is leased and this
  request presents no lease".
- Change: pass the lease on every invoke that touches a resource you leased.

```python
lease = (await client.leases_acquire(["axis-1/motion"], 30_000)).lease
await client.actions_invoke("axis-1", "pulse", {"count": 1}, lease_id=lease.lease_id)   # was: no lease_id
```

- A supplied `leaseId` is now always validated (also by the gateway): an unknown id is `LEASE_EXPIRED`, another
  principal's or one that does not cover the action's resources is `LEASE_CONFLICT`.
- Programs: steps that use a resource held by the program's lease run under it; that lease must cover all resources of
  such a step, or `programs/run` is refused naming the step (BHMS-PRG-006).
- The agent bridge (`bhms_invoke`) acquires and presents leases itself; nothing changes for agents.
- `stop` needs no lease, as before. Retained reads are not blocked by a lease.

## 2. Hazardous actions require a lease (BHMS-DEV-033 is a MUST)

- You will see, when the server builds the description (at `start()`):
  `DescriptionError: action 'spin': a hazardous action must declare requires_lease=True (BHMS-DEV-033)`. A description
  from another implementation that violates it fails schema validation (a gateway does not serve that device).
- Change the declaration, and let callers hold a lease:

```python
@dev.action(effect="hazardous", idempotency="relative", max_duration_ms=10_000,
            requires_lease=True, on_lease_loss="cancel", cancel="supported", resources=["centrifuge-1/rotor"])
async def spin(ctx, ...): ...
```

- Callers of a hazardous action now get `LEASE_REQUIRED` (with the resources in `bound`) until they acquire a lease.

## 3. A failed liveness probe means `offline`

- Before: a liveness probe that returned false or raised at start-up left the device `unknown`. Now it is evidence that
  the device does not answer: the status is `offline`, and new work is refused with `DEVICE_UNAVAILABLE`, until any
  evidence of life arrives (a successful probe, a successful acquisition, a completed action, or `report_alive()`).
- Change: if a device is legitimately not reachable when the server starts, expect `offline` (not `unknown`) in
  `devices/list`; to recover without waiting, enable the periodic probe (`@device.liveness(interval_s=5)` or
  `DeviceServer(liveness_interval_s=5)`, both off by default) or call `device.report_alive()` when your driver reconnects.
- When a device returns to `online`, its reconcile hook is now asked about its `unknown` operations (once per return). A
  driver that triggered reconciliation itself on reconnect can drop that code; the hook must tolerate being called then.

## 4. `BhmsError.code` is now `BhmsError.bhms_code`

- `BhmsError.bhms_code` is the BHMS code (`"OUT_OF_RANGE"`), the same name as on `OperationError` and the wire member
  `bhmsCode`. `BhmsError.code` still works for one release and emits `DeprecationWarning`; under `-W error` (pytest) it
  fails.
- Change: rename `exc.code` to `exc.bhms_code` wherever `exc` is a `BhmsError` (`pytest.raises(BhmsError)` values too).
  `JsonRpcError.code` (the JSON-RPC number) is unchanged.

## Smaller changes

- Property getters receive the device only through a parameter named `device` (or annotated `Device`); any other
  parameter needs a default. `def get(dev): ...` is refused at declaration: rename the parameter to `device`.
- A result outside its declared output range ends the operation `failed` with `OUT_OF_RANGE` (`field: "result.<member>"`)
  instead of `INTERNAL`.
- The `devices/list` `text` filter matches any word (ids and capabilities included) instead of one substring.
- Unknown operations can be resolved by an operator: `bhms resolve <operation>` / `Client.operations_resolve` (scope
  `operations:resolve` or `admin`).
- New units: `{rev}/min`, `{rev}/s`, `mol/L`, `mmol/L`, `umol/L`, `W`, `mW`, `kW`, `[ppm]`, `m3`, `L/h`.

## TypeScript SDK

`sdk/typescript` follows the same rules (Task 8c); its README, section "Migrating to this release", says what changes for
TypeScript code. One difference to note: the TypeScript SDK probed liveness every 15 s by default before this release; it now
probes once at start unless an interval is given, as the Python SDK does.
