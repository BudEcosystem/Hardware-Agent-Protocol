"""UC13: recovery drills at every step of UC4 and UC5.

A drill hits a running task at one point and checks that it ends in one of the three allowed outcome classes, with nothing
silently repeated:

* ``completed``: the agent says ``done`` and the world confirms the goal;
* ``failed_known``: the agent says ``failed`` and nothing it claimed is false (a clean refusal, or a stop at a known step);
* ``unknown_reported``: the agent says ``unknown``: it could not establish what happened and stopped instead of guessing.

Anything else (``done`` the world contradicts, no answer, a duplicate effect, a false certainty) is a ``violation``.

Drill kinds (the *k*-th execution start the agent causes is the trigger; the fault lands 0.2 s of world time later, so
a motion is caught mid-way):

``power_cut``    the device loses power (F3) and gets it back 3 s later;
``partition``    the reply of the operation is lost after the effect happened (F2/F16: the agent must re-ask by key);
``runtime_kill`` the gateway is closed (``Gateway.close()``, a *graceful* shutdown, not SIGKILL) and a new one started on the same
                state directory (F4): it settles what was in flight as ``unknown`` and reconciles; the agent must reconnect and re-ask;
``hand_move``    a person takes the plate or slide away (F9/F14).

Silent ambiguity is measured from the operation records and the agent's own final status (``metrics._ambiguity``); the harness
no longer rewrites an unresolved status to ``unknown`` (the baseline scripts say ``unknown`` themselves when the failing
operation was unknown). The agent under drill is the deterministic baseline script behind ``ResilientClient``, which does what the agent bridge does for
a model: a key on every invoke, the same key on every retry, reconnect after a lost link, a bounded wait for an ``unknown``
operation to be reconciled, and a stop (never a blind second attempt) when it stays unknown or the effect is partial.

Thread-safety: one event loop per drill.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from bhms.protocol.errors import BhmsError
from bhms.transport.base import TransportClosed
from simlab.agents import baseline
from simlab.agents.metrics import TracingClient, compute
from simlab.agents.session import AGENT_SCOPES, Session
from simlab.agents.tasks import Final, load_tasks
from simlab.agents.usecases import CHECKS, SETUPS
from simlab.effects import is_start
from simlab.faults import At, Fault

KINDS = ("power_cut", "partition", "runtime_kill", "hand_move")
FLOWS = {"uc4": "uc4-load-and-image", "uc5": "uc5-serial-dilution"}
TWINS = {"arm-1", "microscope-1", "lh-1", "reader-1", "ledger"}
RECONCILE_WAIT_S = 15.0


class ResilientClient:
    """What a careful agent runtime does around ``actions/invoke`` (the agent bridge does the same for a model)."""

    def __init__(self, session: Session, calls: list[dict[str, Any]]) -> None:
        self.session, self.calls = session, calls
        self.client: Any = None
        self.unresolved: list[str] = []  # operations that stayed unknown or ended with a possible partial effect

    async def connect(self) -> None:
        self.client = TracingClient(await self.session.connect("agent", lossy=True), self.calls)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.client, name)

    async def actions_invoke(self, device_id: str, action: str, arguments: dict[str, Any], **kw: Any) -> Any:
        key = f"drill-{uuid.uuid4().hex[:16]}"
        kw.pop("operation_key", None)
        unavailable = 0
        for attempt in range(40):  # five real attempts plus however many times the device was unavailable
            try:
                result = await asyncio.wait_for(self.client.actions_invoke(device_id, action, arguments, operation_key=key, **kw), 60)
            except (TimeoutError, asyncio.TimeoutError, TransportClosed, ConnectionError, OSError):
                if attempt >= 4 + unavailable:
                    raise
                await self._reconnect()
                continue  # the same key: the runtime answers with the operation it already has (BHMS-OPS-030)
            except BhmsError as exc:
                if exc.bhms_code in ("BUSY", "STALE") and attempt < 4 + unavailable:
                    await asyncio.sleep(0.3)
                    continue
                if exc.bhms_code == "DEVICE_UNAVAILABLE" and not exc.may_have_acted and unavailable < 30:
                    unavailable += 1  # nothing happened (the refusal proves it): wait for the device, then ask again, same key
                    await asyncio.sleep(0.5)
                    continue
                raise
            op = result.operation
            deadline = time.monotonic() + RECONCILE_WAIT_S
            while op.state in ("unknown", "dispatching", "running", "admitted", "queued") and time.monotonic() < deadline:
                try:
                    await asyncio.sleep(0.25)  # an unknown operation is "settled" for operations/wait: do not spin on it
                    op = (await asyncio.wait_for(self.client.operations_wait(op.operation_id, 2000), 10)).operation
                except (TimeoutError, asyncio.TimeoutError, TransportClosed, ConnectionError, OSError):
                    await self._reconnect()
                except BhmsError:
                    await asyncio.sleep(0.3)
            if op.state == "unknown" or (op.state == "failed" and op.error is not None and op.error.may_have_acted):
                self.unresolved.append(f"{device_id}/{action}: {op.state}")
            result.operation = op
            return result
        raise TimeoutError(f"{device_id}/{action}: no answer after five attempts")

    async def _reconnect(self) -> None:
        for _ in range(20):
            try:
                self.client = TracingClient(await self.session.connect("agent", lossy=True), self.calls)
                return
            except Exception:  # the runtime is still starting (HTTP 503), or the port is not up yet
                await asyncio.sleep(0.3)
        raise ConnectionError("the runtime did not come back")


@dataclass
class DrillRecord:
    flow: str
    kind: str
    step: int
    trigger: str
    outcome_class: str
    final_status: str
    zero: dict[str, int]
    success: bool
    unresolved: list[str]
    detail: dict[str, Any]
    wall_s: float


def _install(session: Session, kind: str, step: int, fired: dict[str, Any]) -> None:
    """Arm the drill: when the ``step``-th agent-caused execution start is logged, schedule the fault."""
    world = session.lab.world
    count = {"n": 0}

    def on_effect(effect: Any) -> None:
        if fired or effect.cause is None or effect.device not in TWINS or not is_start(effect.kind):
            return
        count["n"] += 1
        if count["n"] != step:
            return
        device = "lh-1" if effect.device == "ledger" else effect.device
        fired.update(trigger=f"{effect.device}.{effect.kind}", device=device, at=world.time_s)
        at = world.time_s + 0.2
        if kind == "power_cut":
            fault_id = world.faults.inject(Fault(device, "power_loss", At(at)))
            _clear_later(world, fault_id, at + 3.0)
        elif kind == "partition":
            world.faults.inject(Fault(device, "reply_loss", At(at)))
        elif kind == "hand_move":
            container = "slide" if "microscope-1" in session.lab.device_ids.values() else "plate"
            world.faults.inject(Fault(container, "drop_object", At(at)))
        elif kind == "runtime_kill":
            asyncio.get_running_loop().create_task(session.restart_hub())

    world.on_effect(on_effect)


async def _time_passes(world: Any) -> None:
    """In a stepped world time only moves while a device works, so a power cut that "ends after 3 s" would never end while the
    agent waits. Real time keeps passing: advance the world 0.5 s every 0.2 s of wall time while a drill runs."""
    while True:
        await asyncio.sleep(0.2)
        await world.advance(0.5)


def _clear_later(world: Any, fault_id: str, at: float) -> None:
    """Restore the fault's cause (power) once the world clock passes ``at``."""
    handle: dict[str, int] = {}

    def controller(w: Any) -> None:
        if "h" in handle and w.time_s >= at:
            w.remove_controller(handle.pop("h"))
            w.faults.clear(fault_id)
    handle["h"] = world.add_controller(controller)


async def run_drill(flow: str, kind: str, step: int, out: Path, seed: int = 1) -> DrillRecord:
    started = time.perf_counter()
    task = replace(load_tasks()[FLOWS[flow]], ambiguity=True)
    run_dir = out / flow / f"{kind}-{step:03d}"
    fired: dict[str, Any] = {}
    async with await Session.start(run_dir, devices=task.devices, seed=seed, scopes=AGENT_SCOPES) as session:
        lab = session.lab
        SETUPS[task.setup](lab, task, seed)
        mark = session.effect_mark()
        client = ResilientClient(session, [])
        await client.connect()
        _install(session, kind, step, fired)
        passing = asyncio.create_task(_time_passes(lab.world)) if kind == "power_cut" else None
        try:
            final = await asyncio.wait_for(baseline.SCRIPTS[task.scripted](session, client, task, seed), 180)
        except (asyncio.TimeoutError, TimeoutError, BhmsError, TransportClosed, ConnectionError, OSError) as exc:
            final = Final("unknown", {"detail": f"{type(exc).__name__}: {str(exc)[:120]}"})
        if passing is not None:
            passing.cancel()
        outcome = CHECKS[task.check](lab, session, task, final)
        metrics = compute(session, task, final, outcome, client.client, mark)
        zero_ok = not any(metrics.zero.values())
        if final.status == "done" and outcome.success and zero_ok:
            klass = "completed"
        elif final.status == "failed" and zero_ok and not final.status == "none":
            klass = "failed_known"
        elif final.status == "unknown" and zero_ok:
            klass = "unknown_reported"
        else:
            klass = "violation"
        record = DrillRecord(flow, kind, step, fired.get("trigger", "not reached"), klass, final.status, metrics.zero,
                             outcome.success, client.unresolved, {**metrics.detail, "outcome": outcome.detail,
                                                                  "fault_at_s": fired.get("at")}, round(time.perf_counter() - started, 2))
    (run_dir.parent / f"{kind}-{step:03d}.json").write_text(json.dumps(asdict(record), indent=1, default=str))
    return record


async def count_steps(flow: str, out: Path, seed: int = 1) -> int:
    """The number of agent-caused execution starts in the undisturbed flow (the drill points)."""
    task = load_tasks()[FLOWS[flow]]
    async with await Session.start(out / flow / "baseline", devices=task.devices, seed=seed) as session:
        SETUPS[task.setup](session.lab, task, seed)
        client = ResilientClient(session, [])
        await client.connect()
        await baseline.SCRIPTS[task.scripted](session, client, task, seed)
        return sum(1 for e in session.lab.world.effect_log()
                   if e.cause is not None and e.device in TWINS and is_start(e.kind))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="simlab.agents.drills", description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--flows", default="uc4,uc5")
    parser.add_argument("--kinds", default=",".join(KINDS))
    parser.add_argument("--stride", type=int, default=1, help="drill every n-th step (1 = every step)")
    args = parser.parse_args(argv)

    async def go() -> list[DrillRecord]:
        records = []
        for flow in args.flows.split(","):
            steps = await count_steps(flow, args.out)
            print(f"{flow}: {steps} execution starts in the undisturbed flow", flush=True)
            for kind in args.kinds.split(","):
                for step in range(1, steps + 1, args.stride):
                    records.append(await run_drill(flow, kind, step, args.out))
                    if records[-1].outcome_class == "violation":
                        print("  VIOLATION", flow, kind, step, records[-1].final_status, records[-1].zero, records[-1].detail.get("outcome"), flush=True)
        return records

    records = asyncio.run(go())
    table: dict[tuple[str, str], dict[str, int]] = {}
    for r in records:
        row = table.setdefault((r.flow, r.kind), {})
        row[r.outcome_class] = row.get(r.outcome_class, 0) + 1
    for (flow, kind), row in sorted(table.items()):
        print(f"{flow} {kind:13s} {row}")
    (args.out / "drills.json").write_text(json.dumps([asdict(r) for r in records], indent=1, default=str))
    bad = [r for r in records if r.outcome_class == "violation"]
    print(f"{len(records)} drills, {len(bad)} violations")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
