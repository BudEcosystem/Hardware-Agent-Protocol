# Leases and safety

This guide shows, on a running server, what keeps physical work safe in BHMS: leases and fencing, what happens when a
reply is lost (unknown outcomes and how they are resolved), stop, and verified effects. It ends with a checklist for real
hardware. The rules are in [spec 6](../../../spec/bhms/06-operations.md) and [spec 7](../../../spec/bhms/07-leases-and-authority.md);
every block below is executed by the docs test.

BHMS is not a safety system. It does not replace a hardware emergency stop, an over-temperature cutout, a PLC safety
function or a real-time control loop; it carries intent, authority and evidence to and from the devices that run them.

## The device

A bench oven with a hazardous action (`heat_to`, which needs a lease) and an ordinary one (`fan`) on the same resource.
The file `link-down` simulates a lost reply: `after` loses it after the controller accepted the command, `before` loses
it before. Save as `oven_server.py`:

```python file=oven_server.py
import asyncio
import sys
from pathlib import Path

from bhms import Canceled, DeviceServer, Range, Reconciled
from bhms.server import DeviceLost

srv = DeviceServer("bench-oven")
oven = srv.device("oven-1", name="Bench oven", capabilities=["bhms.thermal.heater"], resources=["oven-1/heater"],
                  safety_summary="Heats to 120 Cel. A hardware cutout opens at 130 Cel independently of this server.")
oven.report_alive()
controller = {"setpoint": 25.0}  # the simulated controller's own memory: what reconciliation asks


def link_fault() -> str:
    flag = Path("link-down")
    return flag.read_text().strip() if flag.exists() else ""


@oven.property(unit="Cel", evidence="commanded")
def setpoint() -> float:
    """The setpoint the controller holds."""
    return controller["setpoint"]


@oven.action(effect="hazardous", idempotency="absolute", requires_lease=True, on_lease_loss="cancel",
             cancel="supported", max_duration_ms=10_000)
async def heat_to(ctx, target: Range(25, 120, unit="Cel"), ramp_s: Range(0, 5, unit="s") = 0) -> {"setpoint": "Cel"}:  # noqa: F821
    """Ramp the oven to a setpoint."""
    if link_fault() == "before":
        raise DeviceLost("the controller did not answer (link down before the command was accepted)")
    await ctx.running()
    if await ctx.wait_cancelled(ramp_s):
        raise Canceled(effect="unverified", detail="ramp stopped early")
    controller["setpoint"] = target
    if link_fault() == "after":
        raise DeviceLost("the controller accepted the command, then the reply was lost")
    return {"setpoint": target}


@oven.action(effect="reversible", idempotency="idempotent", max_duration_ms=2000)
async def fan(ctx, on: bool) -> {"on": bool}:  # noqa: F821
    """Switch the circulation fan."""
    return {"on": on}


@oven.on_stop(evidence="reported", max_duration_ms=1000)
async def heater_off(ctx):
    """Commissioned stop: heater off, setpoint back to ambient."""
    controller["setpoint"] = 25.0


@oven.reconcile
async def ask_controller(op):
    """What the controller says happened to an unknown heat_to; None when it cannot tell."""
    if link_fault():
        return None                                     # still no answer: the operation stays unknown
    target = op["arguments"]["target"]
    if op["action"] == "heat_to" and controller["setpoint"] == target:
        return Reconciled("completed", evidence=f"controller setpoint reads {target} Cel", result={"setpoint": target},
                          effect="unverified")
    return None                                         # a different setpoint proves nothing: someone may have changed it


if __name__ == "__main__":
    srv.run(sys.argv[1])
```

```sh run background wait=oven.sock
BHMS_STATE_DIR=$PWD/oven-state python oven_server.py unix:oven.sock
```

## Leases

`heat_to` declares `requires_lease=True` (a hazardous action must). Without a lease it is refused, and the refusal names
the resources a lease must cover. With one, it runs. While the lease is active, *every* action on its resource is refused
unless the request presents the lease, including `fan`, which does not require one, and including the holder itself.

```python run
import asyncio

from bhms import BhmsError
from bhms.client import Client


async def refusal(call):
    try:
        await call
    except BhmsError as error:
        return f"{error.bhms_code} field={error.field} bound={error.bound}"
    return "accepted"


async def main():
    async with await Client.connect("unix:oven.sock") as client:
        print("no lease:", await refusal(client.actions_invoke("oven-1", "heat_to", {"target": 60})))
        lease = (await client.leases_acquire(["oven-1/heater"], ttl_ms=30_000)).lease
        print("lease", lease.state, "fence", lease.fence)
        op = (await client.actions_invoke("oven-1", "heat_to", {"target": 60}, lease_id=lease.lease_id,
                                          operation_key="heat-60", wait_ms=5000)).operation
        print("heat_to:", op.state, op.lease_id == lease.lease_id, op.fence)
        print("fan without the lease:", await refusal(client.actions_invoke("oven-1", "fan", {"on": True})))
        fan = (await client.actions_invoke("oven-1", "fan", {"on": True}, lease_id=lease.lease_id, wait_ms=2000)).operation
        print("fan with the lease:", fan.state)
        released = (await client.leases_release(lease.lease_id)).lease
        print("released:", released.state)
        print("fan after release:", (await client.actions_invoke("oven-1", "fan", {"on": False}, wait_ms=2000)).operation.state)


asyncio.run(main())
```

```text output
no lease: LEASE_REQUIRED field=leaseId bound=['oven-1/heater']
lease active fence ...
heat_to: completed True ...
fan without the lease: LEASE_CONFLICT field=leaseId bound=['oven-1/heater']
fan with the lease: completed
released: released
fan after release: completed
```

`leases_acquire` is all or nothing over its resources and can wait (`wait_ms`) for a conflicting lease to end. A lease
lives for `ttl_ms` unless renewed (`leases_renew`); the server's bounds are in `server/discover`
(`capabilities.leases`). The agent bridge does all of this for a model: it acquires a lease on exactly the resources an
action needs, renews it while the operation runs and releases it when it settles.

## Fencing

Every lease gets a fence, higher than any fence the server issued before (also across restarts). `stop` revokes the
leases on a device; a holder that comes back with the old lease is refused, at admission and again just before dispatch:

```python run
import asyncio

from bhms import BhmsError
from bhms.client import Client


async def main():
    async with await Client.connect("unix:oven.sock") as client:
        old = (await client.leases_acquire(["oven-1/heater"], ttl_ms=30_000)).lease
        stopped = (await client.stop("operator stop", device_ids=["oven-1"])).stops[0]
        print("stop:", stopped.outcome, "revoked", len(stopped.revoked_leases))
        try:
            await client.actions_invoke("oven-1", "heat_to", {"target": 50}, lease_id=old.lease_id)
        except BhmsError as error:
            print("old lease:", error.bhms_code)
        new = (await client.leases_acquire(["oven-1/heater"], ttl_ms=30_000)).lease
        print("new fence is higher:", new.fence > old.fence)
        await client.leases_release(new.lease_id)


asyncio.run(main())
```

```text output
stop: confirmed revoked 1
old lease: FENCED
new fence is higher: True
```

A gateway forwards the upstream lease's fence, and a BHMS-Compact board checks the fence floor itself, so a superseded
holder is refused at every enforcement point between it and the hardware.

## When a reply is lost: unknown outcomes

Simulate a link that drops the reply after the controller accepted the command. The operation becomes `unknown`, not
`failed` and not `completed`: nobody can say whether the oven is heating.

```python run
import asyncio
from pathlib import Path

from bhms import BhmsError
from bhms.client import Client


async def main():
    Path("link-down").write_text("after")
    async with await Client.connect("unix:oven.sock") as client:
        lease = (await client.leases_acquire(["oven-1/heater"], ttl_ms=30_000)).lease
        op = (await client.actions_invoke("oven-1", "heat_to", {"target": 90}, lease_id=lease.lease_id,
                                          operation_key="heat-90", wait_ms=5000)).operation
        print(op.state, op.effect, op.error.bhms_code, op.error.may_have_acted, op.error.retry)
        Path("unknown-op.txt").write_text(op.operation_id)
        try:
            await client.actions_invoke("oven-1", "fan", {"on": True}, lease_id=lease.lease_id)
        except BhmsError as error:
            print("new work on the resource:", error.bhms_code, error.operation_id == op.operation_id)
        await client.leases_release(lease.lease_id)


asyncio.run(main())
```

```text output
unknown unknown DEADLINE_EXCEEDED True after-reconcile
new work on the resource: STALE True
```

Retrying with the same key returns the same `unknown` operation and sends nothing; a new key would be refused with
`STALE` too. The resource stays blocked until evidence arrives. The server asks the device's reconcile hook after a
restart, whenever the device comes back online, and when an operator asks (`bhms resolve` with no `--state`, or
`operations_resolve` with no resolution). While the link is down the device cannot say, so the operation stays unknown
(exit status 3):

```sh run exit=3
bhms resolve unix:oven.sock "$(cat unknown-op.txt)"
```

When the link is back, the controller's own memory is evidence: the hook returns `Reconciled`, and the reconciliation
is recorded, with its evidence, after the unknown entry (which stays in the history):

```sh run
rm link-down
bhms resolve unix:oven.sock "$(cat unknown-op.txt)"
```

```text output
oven-1.heat_to op-... completed: setpoint 90 (effect unverified, ...)
resolved by device evidence: ... controller setpoint reads 90 Cel
```

### When the device can never say

If the reply was lost before the controller accepted the command, its setpoint proves nothing, and the hook returns
`None`. Then a person with authority over the device (scope `operations:resolve` or `admin`; never the agent, and the
agent tools do not offer this) can record what they found. It is recorded as an operator's report, never as a
measurement:

```python run
import asyncio
from pathlib import Path

from bhms.client import Client


async def main():
    Path("link-down").write_text("before")
    async with await Client.connect("unix:oven.sock") as client:
        lease = (await client.leases_acquire(["oven-1/heater"], ttl_ms=30_000)).lease
        op = (await client.actions_invoke("oven-1", "heat_to", {"target": 110}, lease_id=lease.lease_id,
                                          operation_key="heat-110", wait_ms=5000)).operation
        await client.leases_release(lease.lease_id)
        Path("link-down").unlink()
        print(op.state, (await client.operations_resolve(op.operation_id)).operation.state)
        Path("unknown-op.txt").write_text(op.operation_id)


asyncio.run(main())
```

```text output
unknown unknown
```

```sh run
bhms resolve unix:oven.sock "$(cat unknown-op.txt)" --state failed --nothing-happened \
  --basis "J. Doe read the controller display: setpoint 25 Cel, heater relay open, at 14:02"
```

```text output
oven-1.heat_to op-... failed: ...
resolved by operator ...: ...
```

`--nothing-happened` claims proof that the device did not act (`effect: none`, `mayHaveActed: false`). Without that
proof, resolve as `failed` (effect stays `unknown`) or `completed` with `--result` (effect `unverified`). Every
resolution is an `operation.resolved` event naming its source (`device` or `operator`).

## Stop

`stop` runs the commissioned stop procedure (`@oven.on_stop`), cancels queued work, asks running work to end, and revokes
leases. It needs only the `stop` scope and never waits for a lease or a queue. Start a slow ramp, then stop:

```python run
import asyncio

from bhms.client import Client


async def main():
    async with await Client.connect("unix:oven.sock") as client:
        lease = (await client.leases_acquire(["oven-1/heater"], ttl_ms=30_000)).lease
        op = (await client.actions_invoke("oven-1", "heat_to", {"target": 100, "ramp_s": 5}, lease_id=lease.lease_id,
                                          operation_key="ramp-100", wait_ms=200)).operation
        print("before stop:", op.state)
        stop = (await client.stop("door opened", device_ids=["oven-1"], wait_ms=2000)).stops[0]
        print("stop:", stop.outcome, stop.evidence, op.operation_id in stop.cancel_requested_operations)
        settled = (await client.operations_wait(op.operation_id, 5000)).operation
        print("ramp:", settled.state, settled.effect)
        print("setpoint:", (await client.properties_read("oven-1", "setpoint")).observation.value)


asyncio.run(main())
```

```text output
before stop: running
stop: confirmed reported True
ramp: canceled unverified
setpoint: 25.0
```

`confirmed` is reported only with evidence that the stop procedure finished (here `reported`: the procedure returned);
a stop that was sent but not confirmed is `initiated`. A device with no stop procedure reports `unsupported`, and its
work is still cancelled and its leases revoked. From the command line: `bhms stop unix:oven.sock oven-1`, or
`bhms stop --all`.

## Verified effects

`effect: verified` needs an independent measurement. This oven has none (its setpoint is `commanded`, and `heat_to`
has `completion_evidence` at its default, `reported`), so a request that requires a verified effect is refused before anything
heats:

```python run
import asyncio

from bhms import BhmsError
from bhms.client import Client


async def main():
    async with await Client.connect("unix:oven.sock") as client:
        lease = (await client.leases_acquire(["oven-1/heater"], ttl_ms=30_000)).lease
        try:
            await client.actions_invoke("oven-1", "heat_to", {"target": 40}, lease_id=lease.lease_id,
                                        require={"effect": "verified"})
        except BhmsError as error:
            print(error.bhms_code, error.may_have_acted)
        await client.leases_release(lease.lease_id)


asyncio.run(main())
```

```text output
UNSUPPORTED False
```

With a real thermocouple, declare the property `evidence="measured"`, the action `completion_evidence="measured",
verified_by=["temperature"]`, and confirm in the handler with `await ctx.verify("temperature", lambda t: abs(t - target)
< 1.0)`: only a measured, valid reading that passes the check makes the effect `verified`.

## Checklist for real hardware

- A hardware emergency stop that removes power without software. `stop` is not one.
- Bounds in the device's own declarations (`Range`), and limits enforced again in the controller or firmware: an agent
  or a policy can only narrow them.
- `max_duration_ms` that matches the real worst case; `cancel="supported"` only when the handler honours `ctx.cancelled`.
- An `on_stop` procedure for every device that moves or heats, with `evidence="measured"` only if a sensor confirms it.
- Honest evidence labels: `measured` only for an independent sensor; a driver's echo is `reported`, a setpoint
  `commanded`. A failed read raises (or returns `Reading(None, quality="invalid")`), never a default value.
- Raise `DeviceFault(..., proof=...)` with `effect="none"` only when the device proves it did not act (an explicit
  refusal); a lost link is `DeviceLost` (unknown).
- A reconcile hook that asks the device what happened, and returns `None` when it cannot tell.
- `requires_lease=True` and `on_lease_loss` for hazardous actions, and a policy whose principals can stop what they can
  start ([deploying a gateway](gateway.md)).
- A liveness probe (`@device.liveness(interval_s=5)`) so a dead link shows as `offline`.
- Totals enforced in the device: a bound limits one call, and an agent will split a refused amount into allowed calls.
  Keep running totals (dose, reagent, travel per run) in the device or its driver and refuse before acting; gateway
  policy has no cumulative budgets in this version (an open gap, planned for spec v0.2). See
  [connecting agents](connecting-agents.md#a-bound-limits-one-call-not-a-total).
