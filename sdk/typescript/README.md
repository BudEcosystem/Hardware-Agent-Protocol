# @bhms/sdk (TypeScript)

Client, device server and conformance device for the Bhms protocol; behaviour matches the Python reference in `sdk/python`.

## Migrating to this release (hardening round, spec/bhms/CHANGELOG.md "Unreleased")

The TypeScript SDK follows the Python reference (`docs/bhms/migration.md`). What can break code that worked before:

1. **The holder of a lease must present it (BHMS-LSE-014).** While a lease is active on a resource, every action that uses the
   resource is refused unless the request presents that lease, also for actions without `requiresLease` and also for the
   principal that holds it. You will see `LEASE_CONFLICT`, `field: "leaseId"`, `bound` listing the leased resources. Pass the
   lease on every invoke that touches a resource you leased:

   ```ts
   const { lease } = await client.leasesAcquire(["axis-1/motion"], 30_000);
   await client.actionsInvoke("axis-1", "pulse", { count: 1 }, { leaseId: lease.leaseId }); // was: no leaseId
   ```

   A supplied `leaseId` is now always validated (unknown: `LEASE_EXPIRED`; another principal's, or not covering the action's
   resources: `LEASE_CONFLICT`). An operation that queued while the resource was free is rejected if a lease holds the
   resource when it reaches dispatch. Program steps present the program's lease when it holds any of their resources, and
   `programs/run` is refused (naming the step) when that lease covers only part of a step's resources (BHMS-PRG-006). `stop`
   never needs a lease.
2. **Hazardous actions require a lease (BHMS-DEV-033 is a MUST).** `device.action(name, { effect: "hazardous", ... })` without
   `requiresLease: true` throws `DescriptionError` at declaration. Declare the lease (and `onLeaseLoss`, `cancel`); callers then
   get `LEASE_REQUIRED` until they hold one.
3. **A failed liveness probe means `offline`, and periodic probing is opt-in.** A probe that returns false, throws or does not
   answer within `timeoutS` (default 5) makes the device `offline` (new work: `DEVICE_UNAVAILABLE`) until evidence of life: a
   successful probe, a successful acquisition, a completed action or `device.reportAlive()`. The probe runs once at start;
   **this SDK used to probe every 15 s unconditionally**: ask for it with `device.liveness(probe, { intervalS: 15 })` or
   `new DeviceServer(name, { livenessIntervalS: 15 })`.
4. **The reconcile hook also runs when a device returns to `online` (BHMS-OPS-082)**, once per return, bounded by
   `reconcileTimeoutS` (default 10). It must tolerate being called then; return `undefined` when the device cannot say.

Smaller changes: a result outside its declared output range ends `failed` with `OUT_OF_RANGE` (`field: "result.<member>"`)
instead of `INTERNAL`; the `devices/list` `text` filter matches any word (ids and capabilities included) and
`capability: "*"` lists everything (`summaryMatches` now reads `deviceId` from the summary); `UNKNOWN_DEVICE` names
near-miss ids in `hint` and `bound`; unknown operations can be resolved by an operator with `client.operationsResolve(id,
resolution?)` (scope `operations:resolve` or `admin`; recorded as a report, never `verified`), and the server advertises
`capabilities.operations.resolve`; every resolution is an `operation.resolved` event. `BhmsError.bhmsCode` was always the
name of the code in this SDK (Python renamed `code` to `bhms_code` to match); nothing changes there.

## Conformance

Build, then run the Python runner against this SDK's conformance device through its public `--device-command` option:

    npm run build
    bhms conformance conformance-device --device-command "node dist/src/testing/conformanceDevice.js"
    bhms conformance conformance-device:principals --device-command "node dist/src/testing/conformanceDevice.js"

(`scripts/conformance.py` is a wrapper that adds the option for you.) The device accepts
`[URL] [--state-dir DIR] [--memory] [--gateway] [--principals POLICY.json]`.

## State directory lock

One server owns a state directory. On Linux the journal lock is a kernel `flock(2)` held by a `flock(1)` helper process
(util-linux or busybox; no `-E` is needed), so a stdio server opens no listening socket (BHMS-SEC-003). A held lock is retried for up
to two seconds (a restart can race the previous holder's teardown) before the server reports "in use".

If `flock(1)` is missing or refuses its arguments, the server prints a warning on stderr and locks with a listening socket instead
(also what macOS, other Unix and Windows use). **With that fallback a stdio server does hold a listening socket, so BHMS-SEC-003
does not hold**; install util-linux or busybox `flock` to restore it. The two lock kinds do not exclude each other: never run a
flock-locking server and a socket-locking server (for example an older SDK build) on the same state directory.
