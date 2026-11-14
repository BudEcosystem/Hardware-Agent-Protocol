"""The compact profile (spec/bhms/11-compact-binding.md): the endpoint's frame rules, sessions, replay ring, fences and stop, and the
gateway's translation, handles, epochs and reconciliation, proven over the wire against native C endpoints.

Run with ``bhms conformance compact-gateway --profile compact`` (see :mod:`bhms.conformance.compact_fixture`): rows about the
*endpoint* are checked by driving a fresh ``sim_bench`` directly (``raw``); rows about the *gateway* by driving the fixture
gateway over JSON-RPC while the fault-injecting wire records, loses, corrupts and holds frames. The static layout rules
(BHMS-DEV-070/071) are checked against any target by ``compact.layout-rules`` in :mod:`bhms.conformance.checks.descriptions`.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from collections.abc import Callable
from typing import Any

from bhms.conformance.compact_fixture import DEVICE_ID, CompactFixture, RawEndpoint
from bhms.conformance.context import Context
from bhms.conformance.core import check
from bhms.testing.compact_endpoint import TO_DEVICE, TO_GATEWAY, Wire
from bhms.transport import compact as cp

RIG, VOL = f"rig/{DEVICE_ID}", f"vol/{DEVICE_ID}"
LEVEL = (100).to_bytes(2, "little")  # set_level(value=10.0): u16 scale 0.1
MOVE = (20).to_bytes(2, "little") + (1000).to_bytes(2, "little", signed=True)  # move(duration_ms=20, target=10.0)


def fixture(c: Context) -> CompactFixture:
    assert c.target.compact is not None
    return c.target.compact


async def served_fixture(c: Context) -> CompactFixture:
    """The fixture once the gateway lists both endpoints' devices (it says HELLO after it started, so they appear late)."""
    async def listed() -> bool:
        ids = {d["deviceId"] for d in (await c.ok("devices/list", {})).get("devices", [])}
        return {RIG, VOL} <= ids

    c.expect(await until(listed, 15.0), "the gateway never served both compact endpoints", ("BHMS-CMP-011",))
    return fixture(c)


async def until(predicate: Callable[[], Any], timeout: float = 8.0) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = predicate()
        if asyncio.iscoroutine(found):
            found = await found
        if found:
            return found
        await asyncio.sleep(0.03)
    return None


def result_of(incoming: cp.Incoming | None) -> cp.Result | None:
    return incoming.message if incoming is not None and isinstance(incoming.message, cp.Result) else None


def error_of(incoming: cp.Incoming | None) -> cp.Error | None:
    return incoming.message if incoming is not None and isinstance(incoming.message, cp.Error) else None


async def settle_done(raw: RawEndpoint, handle: int, timeout: float = 3.0) -> cp.Result | None:
    """Read frames until the RESULT of ``handle`` arrives (a STARTED operation sends it unprompted)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        got = await raw.reply(deadline - time.monotonic())
        if got is not None and isinstance(got.message, cp.Result) and got.message.handle == handle:
            return got.message
    return None


# ------------------------------------------------------------------------------------------------ the endpoint


@check("compact.endpoint-frame-rules", ["BHMS-CMP-001", "BHMS-CMP-002", "BHMS-CMP-003"], profile="compact", generic=True,
       needs=("compact",))
async def endpoint_frame_rules(c: Context) -> None:
    """Other channels and kinds are ignored without effect; a wrong length is ERROR MALFORMED; frames are never padded."""
    raw = await fixture(c).raw()
    await raw.hello()
    ids = ("BHMS-CMP-001",)
    for channel in (0, 2):
        raw.send(cp.Invoke(1, 0, LEVEL), channel=channel)
    raw.send(cp.Invoke(1, 0, LEVEL), kind=cp.STATUS_KIND)  # a status-kind frame sent toward the endpoint
    c.expect(await raw.silent(), "the endpoint answered a frame on channel 0 or 2 (or of the wrong kind)", ids)
    c.expect(raw.effects("SET") == 0, "a frame on another channel had an effect on the device", ids)
    ids = ("BHMS-CMP-002",)
    exact = {cp.HELLO_REQ: cp.hello_req(1), cp.CANCEL: cp.cancel(1), cp.READ: cp.read(1, 0), cp.STOP: cp.stop(0),
             cp.QUERY: cp.query(1)}
    for kind, payload in exact.items():
        for broken in (payload[:-1], payload + b"\x00"):
            raw.send(broken)
            got = error_of(await raw.reply(1.0))
            c.expect(got is not None and got.code == cp.E_MALFORMED and got.request_type == kind,
                     f"message type 0x{kind:02x} with {len(broken)} bytes (exact length {len(payload)}) was not answered "
                     f"ERROR MALFORMED: {got}", ids)
    short = cp.invoke(1, 0, LEVEL)[:9]  # the fixed part of INVOKE is 10 bytes
    for payload in (short, cp.invoke(1, 0, LEVEL[:1]), cp.invoke(1, 0, LEVEL + b"\x00")):
        raw.send(payload)
        got = error_of(await raw.reply(1.0))
        c.expect(got is not None and got.code == cp.E_MALFORMED, f"an INVOKE of {len(payload)} bytes with a wrong layout length "
                 f"was not answered ERROR MALFORMED: {got}", ids)
    c.expect(raw.effects("SET") == 0, "a malformed INVOKE had an effect", ids)
    ids = ("BHMS-CMP-003",)
    frames = [raw.send(cp.invoke(2, 0, LEVEL))]
    seen = []
    while (got := await raw.reply(1.0)) is not None:
        seen.append(got)
        if isinstance(got.message, cp.Result):
            break
    c.expect(seen, "no reply to a valid INVOKE", ids)
    for item in [*seen, *(cp.Incoming(None, None, w) for w in frames)]:
        payload = (cp.decode(_unstuff(item.wire)[20:-2]).encode() if item.frame is None else item.frame.payload)
        stuffed = item.wire.count(0x7D)
        c.expect(len(item.wire) == 24 + len(payload) + stuffed,
                 f"a frame of {len(payload)} payload bytes and {stuffed} stuffed octets is {len(item.wire)} bytes on the wire, "
                 f"not {24 + len(payload) + stuffed} (BHMS-CMP-003: no padding)", ids)
    c.expect(len(frames[0]) <= 64, f"a typical INVOKE is {len(frames[0])} bytes on the wire (limit 64)", ids)


def _unstuff(wire: bytes) -> bytes:
    out, it = bytearray(), iter(wire[1:-1])
    for byte in it:
        out.append(next(it) ^ 0x20 if byte == 0x7D else byte)
    return bytes(out)


@check("compact.endpoint-sessions", ["BHMS-CMP-021", "BHMS-CMP-023"], profile="compact", generic=True, needs=("compact",))
async def endpoint_sessions(c: Context) -> None:
    """A wrong session is SESSION_MISMATCH without effect (STOP excepted); NEW_SESSION is honoured only when idle."""
    raw = await fixture(c).raw()
    hello = await raw.hello()
    wrong = hello.epoch + 5
    for message in (cp.Invoke(1, 0, LEVEL), cp.Read(1, 0), cp.Cancel(1), cp.Query(1)):
        got = await raw.exchange(message, session=wrong)
        error = error_of(got)
        c.expect(error is not None and error.code == cp.E_SESSION_MISMATCH,
                 f"{type(message).__name__} with a wrong session was not refused SESSION_MISMATCH: {got and got.message}",
                 ("BHMS-CMP-021",))
    c.expect(raw.effects("SET") == 0, "an INVOKE with a wrong session had an effect", ("BHMS-CMP-021",))
    got = await raw.exchange(cp.Stop(0), session=wrong)
    c.expect(got is not None and isinstance(got.message, cp.StopAck), f"STOP with a wrong session was not honoured: {got and got.message}",
             ("BHMS-CMP-021",))
    await raw.drain(0.5)  # the delayed confirmation of that stop
    before = hello
    again = await raw.hello(new_session=True)
    c.expect(again.epoch != before.epoch, "NEW_SESSION while idle did not start a new epoch", ("BHMS-CMP-023",))
    if before.persistent:
        c.expect(again.epoch == (before.epoch + 1) % 2**32 or again.epoch > before.epoch,
                 f"a persistent epoch must increase: {before.epoch} -> {again.epoch}", ("BHMS-CMP-023",))
    c.expect(again.last_handle == 0, "NEW_SESSION did not reset lastHandle", ("BHMS-CMP-023",))
    first = result_of(await raw.exchange(cp.Invoke(1, 0, LEVEL)))
    c.expect(first is not None and first.state == cp.ST_COMPLETED, "handle 1 did not run again after NEW_SESSION cleared the ring",
             ("BHMS-CMP-023",))
    started = await raw.exchange(cp.Invoke(2, 3, (3000).to_bytes(2, "little")))  # lock: stays active
    c.expect(isinstance(started and started.message, cp.Status), f"lock did not start: {started and started.message}",
             ("BHMS-CMP-023",))
    ignored = await raw.hello(new_session=True)
    c.expect(ignored.epoch == again.epoch, "NEW_SESSION was honoured while an operation was active", ("BHMS-CMP-023",))


@check("compact.endpoint-replay-ring", ["BHMS-CMP-031", "BHMS-CMP-032", "BHMS-CMP-035"], profile="compact", generic=True,
       needs=("compact",))
async def endpoint_replay_ring(c: Context) -> None:
    """The ring holds at least 4 handles: identical retransmits are answered from it, conflicts and evictions are refused."""
    raw = await fixture(c).raw()
    hello = await raw.hello()
    c.expect(hello.ring >= 4, f"the replay ring holds {hello.ring} handles; BHMS-CMP-031 needs at least 4", ("BHMS-CMP-031",))
    results: dict[int, cp.Result] = {}
    for handle in range(1, 5):
        got = result_of(await raw.exchange(cp.Invoke(handle, 0, (handle * 10).to_bytes(2, "little"))))
        c.expect(got is not None and got.state == cp.ST_COMPLETED, f"handle {handle} did not complete", ("BHMS-CMP-031",))
        results[handle] = got  # type: ignore[assignment]
    ran = raw.effects("SET")
    for handle in range(1, 5):  # the last four, retransmitted identically
        again = result_of(await raw.exchange(cp.Invoke(handle, 0, (handle * 10).to_bytes(2, "little"))))
        c.expect(again == results[handle], f"the retransmitted INVOKE {handle} was not answered with its stored RESULT: {again}",
                 ("BHMS-CMP-031", "BHMS-CMP-032"))
    c.expect(raw.effects("SET") == ran, "a retransmitted INVOKE acted again", ("BHMS-CMP-032",))
    conflict = error_of(await raw.exchange(cp.Invoke(4, 0, (99).to_bytes(2, "little"))))
    c.expect(conflict is not None and conflict.code == cp.E_HANDLE_CONFLICT, f"same handle, other payload: {conflict}",
             ("BHMS-CMP-032",))
    for handle in (5, 6):
        await raw.exchange(cp.Invoke(handle, 0, LEVEL))
    evicted = error_of(await raw.exchange(cp.Invoke(1, 0, (10).to_bytes(2, "little"))))
    c.expect(evicted is not None and evicted.code == cp.E_HANDLE_UNKNOWN, f"an evicted handle must be HANDLE_UNKNOWN: {evicted}",
             ("BHMS-CMP-032",))
    c.expect(raw.effects("SET") == ran + 2, "a conflicting or evicted INVOKE acted", ("BHMS-CMP-032",))
    # BHMS-CMP-035: an asynchronous RESULT is sent once unprompted, again for QUERY and for a retransmitted INVOKE
    lock = cp.Invoke(7, 3, (250).to_bytes(2, "little"))
    first = await raw.exchange(lock)
    c.expect(first is not None and isinstance(first.message, cp.Status), f"lock did not report STATUS: {first and first.message}",
             ("BHMS-CMP-035",))
    unprompted = await settle_done(raw, 7)
    c.expect(unprompted is not None and unprompted.state == cp.ST_COMPLETED, "no RESULT arrived unprompted", ("BHMS-CMP-035",))
    c.expect(not await raw.drain(0.4), "the RESULT was sent more than once unprompted", ("BHMS-CMP-035",))
    for message in (cp.Query(7), lock):
        again = result_of(await raw.exchange(message))
        c.expect(again == unprompted, f"{type(message).__name__} was not answered with the RESULT again: {again}", ("BHMS-CMP-035",))


@check("compact.endpoint-fences", ["BHMS-CMP-040"], profile="compact", generic=True, needs=("compact",))
async def endpoint_fences(c: Context) -> None:
    """Fence 0 on a lease action is LEASE_REQUIRED; a fence below the floor is FENCED; a higher fence raises the floor."""
    raw = await fixture(c).raw()
    hello = await raw.hello()
    if not hello.fencing:
        c.not_applicable("the endpoint does not advertise FENCING")

    async def move(handle: int, fence: int) -> cp.Incoming | None:
        got = await raw.exchange(cp.Invoke(handle, 1, MOVE, fence))
        if got is not None and isinstance(got.message, cp.Status):
            await settle_done(raw, handle)
        return got

    got = error_of(await move(1, 0))
    c.expect(got is not None and got.code == cp.E_LEASE_REQUIRED, f"fence 0 on a lease action: {got}", ("BHMS-CMP-040",))
    accepted = await move(2, 10)
    c.expect(accepted is not None and isinstance(accepted.message, cp.Status | cp.Result), f"fence 10 refused: {accepted and accepted.message}",
             ("BHMS-CMP-040",))
    low = error_of(await move(3, 5))
    c.expect(low is not None and low.code == cp.E_FENCED, f"a fence below the floor must be FENCED: {low}", ("BHMS-CMP-040",))
    await move(4, 20)  # raises the floor
    old = error_of(await move(5, 10))
    c.expect(old is not None and old.code == cp.E_FENCED, f"the floor did not rise to 20: {old}", ("BHMS-CMP-040",))


@check("compact.endpoint-stop", ["BHMS-CMP-050", "BHMS-CMP-051"], profile="compact", generic=True, needs=("compact",))
async def endpoint_stop(c: Context) -> None:
    """STOP is answered first with any session, confirmed later, ends active operations and fences older lease holders; a HELLO
    drops the token of a stop in progress."""
    raw = await fixture(c).raw()
    hello = await raw.hello()
    if not hello.stop_supported:
        c.not_applicable("the endpoint advertises no stop procedure")
    await raw.exchange(cp.Invoke(1, 1, (3000).to_bytes(2, "little") + (500).to_bytes(2, "little", signed=True), 7))
    started = await raw.exchange(cp.Invoke(2, 3, (3000).to_bytes(2, "little")))
    c.expect(isinstance(started and started.message, cp.Status), "the long operation did not start", ("BHMS-CMP-050",))
    raw.send(cp.Stop(0, 0x5A), session=hello.epoch + 9)
    frames = [await raw.reply(2.0)]
    first = frames[0]
    c.expect(first is not None and isinstance(first.message, cp.StopAck), f"STOP was not acknowledged before anything else: {first and first.message}",
             ("BHMS-CMP-050",))
    while (got := await raw.reply(1.0)) is not None:
        frames.append(got)
        if isinstance(got.message, cp.StopAck) and got.message.outcome == cp.STOPACK_CONFIRMED:
            break
    acks = [f.message for f in frames if f and isinstance(f.message, cp.StopAck)]
    c.expect(acks and all(a.token == 0x5A for a in acks), f"every STOP_ACK must echo the STOP's token 0x5A: {acks}", ("BHMS-CMP-050",))
    if first is not None and isinstance(first.message, cp.StopAck) and first.message.outcome == cp.STOPACK_INITIATED:
        c.expect(len(acks) == 2 and acks[1].outcome == cp.STOPACK_CONFIRMED and frames[-1].kind == cp.TELEMETRY,
                 f"an initiated stop must be followed by a confirming STOP_ACK (kind 03): {acks}", ("BHMS-CMP-050",))
    ended = {f.message.handle: f.message.state for f in frames if f and isinstance(f.message, cp.Result)}
    c.expect(ended.get(1) in (cp.ST_CANCELED, cp.ST_FAILED) and ended.get(2) in (cp.ST_CANCELED, cp.ST_FAILED),
             f"STOP must end every active operation (canceled or failed): {ended}", ("BHMS-CMP-051",))
    fenced = error_of(await raw.exchange(cp.Invoke(3, 1, MOVE, 7)))
    c.expect(fenced is not None and fenced.code == cp.E_FENCED, f"a pre-stop fence must be FENCED after STOP: {fenced}", ("BHMS-CMP-051",))
    if first is None or not isinstance(first.message, cp.StopAck) or first.message.outcome != cp.STOPACK_INITIATED:
        return  # a stop confirmed at once leaves nothing pending across a HELLO
    # A stop still in progress when the endpoint says HELLO is nobody's afterwards: its confirming ack carries token 0, so the
    # stop of a restarted gateway that reuses the token cannot be confirmed by it.
    raw.send(cp.Stop(0, 0x33))
    raw.nonce += 1
    raw.send(cp.HelloReq(raw.nonce, 0), session=0)  # right behind the STOP: answered before the stop can finish
    after: list[cp.Incoming] = []
    while (got := await raw.reply(2.0)) is not None:
        after.append(got)
        if isinstance(got.message, cp.StopAck) and got.message.outcome == cp.STOPACK_CONFIRMED:
            break
    kinds = [type(f.message).__name__ for f in after]
    said_hello = next((i for i, f in enumerate(after) if isinstance(f.message, cp.Hello)), None)
    c.expect(said_hello is not None and isinstance(after[-1].message, cp.StopAck) and after[-1].message.outcome == cp.STOPACK_CONFIRMED,
             f"STOP then HELLO_REQ must be answered by STOP_ACK initiated, HELLO and the confirming STOP_ACK: {kinds}", ("BHMS-CMP-050",))
    if said_hello is not None and said_hello < len(after) - 1:
        late = [f.message for f in after[said_hello + 1:] if isinstance(f.message, cp.StopAck)]
        c.expect(all(a.token == 0 for a in late),
                 f"a STOP_ACK sent after a HELLO for a stop received before it must carry token 0, not the stop's token: {late}",
                 ("BHMS-CMP-050",))


@check("compact.endpoint-value-quality", ["BHMS-CMP-060"], profile="compact", generic=True, needs=("compact",))
async def endpoint_value_quality(c: Context) -> None:
    """A property that cannot be measured is VALUE invalid with no value bytes."""
    raw = await fixture(c).raw()
    await raw.hello()
    good = await raw.exchange(cp.Read(1, 1, cp.READ_FRESH))
    c.expect(good is not None and isinstance(good.message, cp.Value) and good.message.quality == cp.Q_VALID and len(good.message.raw) == 4,
             f"a connected sensor must read valid with 4 value bytes: {good and good.message}", ("BHMS-CMP-060",))
    await raw.exchange(cp.Invoke(1, 4, b"\x00"))  # sensor(connected=false)
    bad = await raw.exchange(cp.Read(2, 1, cp.READ_FRESH))
    c.expect(bad is not None and isinstance(bad.message, cp.Value) and bad.message.quality in (cp.Q_INVALID, cp.Q_UNKNOWN)
             and bad.message.raw == b"", f"a disconnected sensor must read invalid with no value bytes: {bad and bad.message}",
             ("BHMS-CMP-060",))


# ------------------------------------------------------------------------------------------------ the gateway


def invokes(wire: Wire, since: int = 0) -> list[Any]:
    return [s for s in wire.log[since:] if isinstance(s.message, cp.Invoke) and s.direction == TO_DEVICE]


async def lease(c: Context, device: str) -> dict[str, Any]:
    return (await c.ok("leases/acquire", {"resources": [f"{device}/axis"], "ttlMs": 30_000}))["lease"]


@check("compact.gateway-refuses-lossy-values", ["BHMS-CMP-010"], profile="compact", generic=True, needs=("compact",))
async def gateway_refuses_lossy(c: Context) -> None:
    """A value the wire cannot carry exactly is refused before anything is sent: never rounded, clamped or truncated."""
    wire = (await served_fixture(c)).wires["rig"]
    mark = len(wire.log)
    for value, code in ((50.05, "INVALID_ARGUMENT"), (100.5, "OUT_OF_RANGE"), (-0.1, "OUT_OF_RANGE")):
        got = await c.invoke(RIG, "set_level", {"value": value}, waitMs=2000)
        c.refused(got, code, what=f"set_level({value})", ids=("BHMS-CMP-010",))
    c.expect(not invokes(wire, mark), "a refused value reached the wire as an INVOKE", ("BHMS-CMP-010",))
    ok = await c.run(RIG, "set_level", {"value": 50.1}, waitMs=3000)
    c.expect(ok["state"] == "completed" and invokes(wire, mark)[-1].message.args == (501).to_bytes(2, "little"),
             "50.1 must travel as the integer 501, exactly", ("BHMS-CMP-010",))


@check("compact.gateway-layout-indices", ["BHMS-CMP-011"], profile="compact", generic=True, needs=("compact",))
async def gateway_layout_indices(c: Context) -> None:
    """Action indices on the wire are the layout's, whatever the order of the names."""
    wire = (await served_fixture(c)).wires["rig"]
    description = await c.describe(RIG)
    layout = {name: action["compact"]["index"] for name, action in description["actions"].items()}
    c.expect(sorted(description["actions"], key=layout.get) != sorted(description["actions"]),
             "this fixture's indices must differ from alphabetical order to prove anything", ("BHMS-CMP-011",))
    held = await lease(c, RIG)
    for name, arguments in (("lock", {"duration_ms": 20}), ("sensor", {"connected": True}), ("probe", {"mode": 0}),
                            ("set_level", {"value": 1.0}), ("move", {"duration_ms": 20, "target": 1.0})):
        mark = len(wire.log)
        members = {"leaseId": held["leaseId"]} if name == "move" else {}
        done = await c.run(RIG, name, arguments, waitMs=3000, **members)
        c.expect(done["state"] == "completed", f"{name} ended {done['state']}", ("BHMS-CMP-011",))
        sent = invokes(wire, mark)
        c.expect(sent and sent[0].message.action == layout[name],
                 f"{name} must be sent as action index {layout[name]}, was {sent and sent[0].message.action}", ("BHMS-CMP-011",))
    await c.ok("leases/release", {"leaseId": held["leaseId"]})


@check("compact.gateway-handles-and-fences", ["BHMS-CMP-030", "BHMS-CMP-041"], profile="compact", generic=True, needs=("compact",))
async def gateway_handles_and_fences(c: Context) -> None:
    """Handles increase by one per epoch and are journaled before the send; fences only grow."""
    fx = await served_fixture(c)
    wire = fx.wires["rig"]
    mark = len(wire.log)
    for _ in range(3):
        await c.run(RIG, "set_level", {"value": 2.0}, waitMs=3000)
    handles = [s.message.handle for s in invokes(wire, mark)]
    c.expect(handles == list(range(handles[0], handles[0] + 3)), f"handles must increase by one: {handles}", ("BHMS-CMP-030",))
    wire.hold(TO_DEVICE)  # the INVOKE reaches the wire but never the endpoint: what is recorded must already be durable
    try:
        mark = len(wire.log)
        op = await c.invoke_op(RIG, "set_level", {"value": 3.0}, waitMs=0)
        sent = await until(lambda: invokes(wire, mark))
        c.expect(sent, "the INVOKE was never sent", ("BHMS-CMP-030",))
        db = sqlite3.connect(f"file:{c.target.state_dir}/compact/compact-rig.sqlite3?mode=ro", uri=True)
        try:
            rows = db.execute("SELECT key, value FROM meta WHERE key LIKE ?", (f"compact/{DEVICE_ID}/ops/%",)).fetchall()
        finally:
            db.close()
        recorded = [json.loads(v) for _, v in rows]
        c.expect(any(r["handle"] == sent[0].message.handle and r["epoch"] == sent[0].session for r in recorded),
                 f"handle {sent[0].message.handle} was on the wire but is not journaled with its epoch: {recorded}", ("BHMS-CMP-030",))
    finally:
        wire.release(TO_DEVICE)
        await c.settle(op["operationId"])
    fences = []
    for _ in range(3):
        held = await lease(c, RIG)
        mark = len(wire.log)
        await c.run(RIG, "move", {"duration_ms": 20, "target": 1.0}, waitMs=3000, leaseId=held["leaseId"])
        fences.append(invokes(wire, mark)[0].message.fence)
        await c.ok("leases/release", {"leaseId": held["leaseId"]})
    c.expect(fences == sorted(set(fences)) and fences[0] > 0, f"fences must be non-zero and strictly increasing: {fences}", ("BHMS-CMP-041",))


@check("compact.gateway-new-session-before-exhaustion", ["BHMS-CMP-030"], profile="compact", generic=True, needs=("compact", "restart"),
       timeout=90)
async def gateway_new_session(c: Context) -> None:
    """Handles never wrap: a new session starts before handle 65535 (the journaled counter is moved to just below the limit)."""
    from bhms.runtime.store import Store

    fx = await served_fixture(c)
    wire = fx.wires["rig"]
    epoch = max((s.message.epoch for s in wire.log if isinstance(s.message, cp.Hello)), default=None)
    c.expect(epoch is not None, "the gateway never said HELLO to the endpoint")
    await c.target.stop_base()
    store = Store(f"{c.target.state_dir}/compact/compact-rig.sqlite3")
    try:
        store.meta_set(f"compact/{DEVICE_ID}/link", json.dumps({"epoch": epoch, "persistent": True, "next_handle": 64_999}),
                       barrier=True)
    finally:
        store.close()
    await c.reconnect_base(await c.target.restart())
    await c.locate()
    await served_fixture(c)
    mark = len(wire.log)
    for _ in range(2):
        done = await c.run(RIG, "set_level", {"value": 4.0}, waitMs=5000)
        c.expect(done["state"] == "completed", f"an operation near the handle limit ended {done['state']}", ("BHMS-CMP-030",))
    sent = invokes(wire, mark)
    requests = [s for s in wire.log[mark:] if isinstance(s.message, cp.HelloReq) and s.message.new_session]
    c.expect(requests, "the gateway never began a new session before handle 65535", ("BHMS-CMP-030",))
    c.expect(sent[0].message.handle == 64_999 and sent[-1].message.handle == 1 and sent[-1].session != sent[0].session,
             f"the handles must restart at 1 in the new epoch: {[(s.session, s.message.handle) for s in sent]}", ("BHMS-CMP-030",))


@check("compact.gateway-observation-epoch", ["BHMS-CMP-060"], profile="compact", generic=True, needs=("compact",))
async def gateway_observation(c: Context) -> None:
    """The observation carries the boot epoch and the VALUE sequence; an unmeasurable value stays invalid, never substituted."""
    wire = (await served_fixture(c)).wires["rig"]
    mark = len(wire.log)
    good = (await c.ok("properties/read", {"deviceId": RIG, "property": "temp", "fresh": True}))["observation"]
    frames = [s for s in wire.log[mark:] if isinstance(s.message, cp.Value)]
    c.expect(frames, "the read produced no VALUE on the wire", ("BHMS-CMP-060",))
    value = frames[-1]
    c.expect(good["epoch"] == f"compact:{value.session}" and good["sequence"] == value.message.sequence,
             f"Observation epoch/sequence must be the endpoint's boot epoch and VALUE sequence: {good['epoch']}/{good['sequence']} "
             f"vs {value.session}/{value.message.sequence}", ("BHMS-CMP-060",))
    await c.run(RIG, "sensor", {"connected": False}, waitMs=3000)
    try:
        bad = (await c.ok("properties/read", {"deviceId": RIG, "property": "temp", "fresh": True}))["observation"]
        c.expect(bad["quality"] == "invalid" and bad.get("value") is None,
                 f"a disconnected sensor must read invalid with no value: {bad}", ("BHMS-CMP-060",))
    finally:
        await c.run(RIG, "sensor", {"connected": True}, waitMs=3000)


@check("compact.gateway-lost-reply", ["BHMS-CMP-033"], profile="compact", generic=True, needs=("compact",), timeout=90)
async def gateway_lost_reply(c: Context) -> None:
    """A lost RESULT: a persistent endpoint gets the same INVOKE again, any other endpoint is only ever sent QUERY."""
    fx = await served_fixture(c)
    try:
        for name, device, persistent in (("rig", RIG, True), ("vol", VOL, False)):
            wire = fx.wires[name]
            mark = len(wire.log)
            wire.drop(TO_GATEWAY, match=lambda m: isinstance(m, cp.Result))
            done = await c.run(device, "set_level", {"value": 6.0}, waitMs=5000)
            c.expect(done["state"] == "completed", f"{name}: the operation ended {done['state']} after a lost RESULT", ("BHMS-CMP-033",))
            sent = invokes(wire, mark)
            queries = [s for s in wire.log[mark:] if isinstance(s.message, cp.Query) and s.direction == TO_DEVICE
                       and s.message.handle == sent[0].message.handle]
            if persistent:
                c.expect(len(sent) == 2 and sent[0].message == sent[1].message,
                         f"a persistent endpoint must be sent the same INVOKE again: {[s.message for s in sent]}", ("BHMS-CMP-033",))
            else:
                c.expect(len(sent) == 1 and queries,
                         f"an endpoint without a persistent epoch must never be sent the INVOKE again, only QUERY: "
                         f"{len(sent)} INVOKE, {len(queries)} QUERY", ("BHMS-CMP-033",))
            c.expect(fx.endpoints[name].count("SET") >= 1, f"{name}: the action never ran")
    finally:
        fx.clear_faults()


async def events_of(c: Context, device: str, type_: str) -> list[dict[str, Any]]:
    page = await c.ok("events/read", {"deviceId": device, "limit": 200})
    return [e for e in page["events"] if e["type"] == type_]


@check("compact.gateway-reboot-and-epochs", ["BHMS-CMP-020", "BHMS-CMP-022"], profile="compact", generic=True, needs=("compact",),
       timeout=120)
async def gateway_reboots(c: Context) -> None:
    """A persistent epoch increases at every reboot; an operation in flight at a reset becomes unknown, device.epoch is emitted and
    nothing is sent twice; an endpoint without a persistent epoch is treated as reset although its epoch repeats."""
    fx = await served_fixture(c)
    wire = fx.wires["rig"]
    def hellos() -> list[int]:
        return [s.message.epoch for s in wire.log if isinstance(s.message, cp.Hello)]

    epochs = hellos()
    for _ in range(3):
        before = len(hellos())
        await wire.reboot()
        seen = await until(lambda: hellos()[before:], 10)
        c.expect(seen, "the gateway did not say HELLO again after a reboot", ("BHMS-CMP-020",))
        await asyncio.sleep(0.6)
    epochs = hellos()[len(epochs) - 1:]  # the epoch before the first reboot, then one per reboot
    c.expect(all(b > a for a, b in zip(epochs, epochs[1:])), f"a persistent epoch must increase at every reboot: {epochs}", ("BHMS-CMP-020",))
    for name, device, persistent in (("rig", RIG, True), ("vol", VOL, False)):
        wire = fx.wires[name]
        mark = len(wire.log)
        begun = fx.endpoints[name].count("LOCK-start")
        op = await c.invoke_op(device, "lock", {"duration_ms": 5000}, waitMs=0)
        c.expect(await until(lambda: fx.endpoints[name].count("LOCK-start") > begun), f"{name}: the lock never started")
        await wire.reboot()  # the operation is gone with the power
        settled = await c.settle(op["operationId"], 20)
        c.expect(settled["state"] == "unknown" and settled["error"]["mayHaveActed"] is True,
                 f"{name}: an operation in flight at a reset must be unknown, was {settled['state']}", ("BHMS-CMP-022",))
        c.expect(len(invokes(wire, mark)) == 1, f"{name}: the INVOKE was sent {len(invokes(wire, mark))} times; a reset operation is never re-sent",
                 ("BHMS-CMP-022",))
        if persistent:
            emitted = await until(lambda: events_of(c, device, "device.epoch"))
            c.expect(emitted, "no device.epoch event after the epoch changed", ("BHMS-CMP-022",))
            async def freed() -> bool:  # the proof reaches the gateway as the endpoint's device.epoch event, a moment after the reply
                return not await _inhibited(c, device)

            c.expect(await until(freed, 10),
                     "a persistent epoch advanced, which proves the old work purged: the resource inhibition must be lifted",
                     ("BHMS-CMP-022",))
        else:
            c.expect(await _inhibited(c, device),
                     "the epoch of an endpoint without a persistent counter repeats: no proof, the inhibition must stay (BHMS-OPS-042)",
                     ("BHMS-CMP-020", "BHMS-CMP-022"))
            stop = await c.ok("stop", {"reason": "compact conformance", "deviceIds": [device], "waitMs": 3000})
            c.expect(stop["stops"][0]["outcome"] == "confirmed", f"{name}: stop was not confirmed: {stop}")
            c.expect(not await _inhibited(c, device), "a confirmed stop must lift the inhibition (BHMS-OPS-042)", ("BHMS-CMP-022",))


async def _inhibited(c: Context, device: str) -> bool:
    got = await c.invoke(device, "lock", {"duration_ms": 20}, waitMs=3000)  # lock holds bench-rig/axis: the resource of the unknown operation
    if got.result is not None:
        return False
    c.expect(got.code == "STALE", f"{device}: expected STALE from an inhibited resource, got {got.describe()}")
    return True


@check("compact.gateway-restart-reconciles", ["BHMS-CMP-034"], profile="compact", generic=True, needs=("compact", "restart"),
       timeout=90)
async def gateway_restart(c: Context) -> None:
    """After a gateway restart the operation is QUERYed in the same epoch and settled from the endpoint's RESULT, never re-sent;
    a QUERY above lastHandle is HANDLE_UNKNOWN without acting."""
    fx = await served_fixture(c)
    wire = fx.wires["rig"]
    mark = len(wire.log)
    begun = fx.endpoints["rig"].count("LOCK-start")
    op = await c.invoke_op(RIG, "lock", {"duration_ms": 1500}, waitMs=0)
    c.expect(await until(lambda: fx.endpoints["rig"].count("LOCK-start") > begun), "the lock never started")
    handle = invokes(wire, mark)[0].message.handle
    await c.reconnect_base(await c.target.restart(kill=True))
    await c.locate()
    settled = await c.settle(op["operationId"], 30, states=frozenset({"completed", "failed", "canceled", "rejected"}))
    c.expect(settled["state"] == "completed", f"the operation must be reconciled from the endpoint's RESULT, was {settled['state']}",
             ("BHMS-CMP-034",))
    c.expect(any(isinstance(s.message, cp.Query) and s.message.handle == handle for s in wire.log[mark:]),
             "the gateway never sent QUERY for the operation after its restart", ("BHMS-CMP-034",))
    c.expect(len(invokes(wire, mark)) == 1 and fx.endpoints["rig"].count("LOCK-start") == begun + 1,
             "the restarted gateway sent the command again", ("BHMS-CMP-034",))
    raw = await fx.raw()
    hello = await raw.hello()
    unknown = error_of(await raw.exchange(cp.Query(hello.last_handle + 40)))
    c.expect(unknown is not None and unknown.code == cp.E_HANDLE_UNKNOWN and raw.effects("SET") == 0,
             f"QUERY of a handle above lastHandle must be HANDLE_UNKNOWN without acting: {unknown}", ("BHMS-CMP-034",))


@check("compact.gateway-stop-token", ["BHMS-CMP-050"], profile="compact", generic=True, needs=("compact",), timeout=60)
async def gateway_stop_token(c: Context) -> None:
    """Only a STOP_ACK echoing the token of the gateway's own STOP confirms it: acks with another token or the reserved token 0
    (an endpoint-originated stop) are not evidence, even when they say confirmed/measured."""
    wire = (await served_fixture(c)).wires["rig"]
    wire.drop(TO_GATEWAY, count=1000, match=lambda m: isinstance(m, cp.StopAck))  # the endpoint's own acks never arrive
    epoch = max((s.message.epoch for s in wire.log if isinstance(s.message, cp.Hello)), default=0)
    mark = len(wire.log)

    async def forge() -> None:
        while True:
            sent = [s.message.token for s in wire.log[mark:] if isinstance(s.message, cp.Stop) and s.direction == TO_DEVICE]
            for token in {0, *((t % 255 + 1) for t in sent)} - set(sent):
                ack = cp.StopAck(cp.STOPACK_CONFIRMED, cp.EVIDENCE_MEASURED, 0, token)
                wire.inject(TO_GATEWAY, wire.frame_for(ack, epoch, kind=cp.STATUS_KIND))
            await asyncio.sleep(0.05)

    forger = asyncio.get_running_loop().create_task(forge())
    try:
        got = await c.ok("stop", {"reason": "compact conformance: forged acks", "deviceIds": [RIG], "waitMs": 3000})
    finally:
        forger.cancel()
        await asyncio.gather(forger, return_exceptions=True)
        wire.clear_rules()
    c.expect(got["stops"][0]["outcome"] != "confirmed",
             f"a STOP_ACK with a foreign token or token 0 must not confirm a gateway stop: {got['stops'][0]}", ("BHMS-CMP-050",))
    sent = [s.message for s in wire.log[mark:] if isinstance(s.message, cp.Stop)]
    c.expect(sent and all(m.token != 0 for m in sent), f"the gateway's STOP must carry a non-zero token: {sent}", ("BHMS-CMP-050",))
    mark = len(wire.log)
    real = await c.ok("stop", {"reason": "compact conformance: real acks", "deviceIds": [RIG], "waitMs": 3000})
    c.expect(real["stops"][0]["outcome"] == "confirmed", f"a genuine echoed ack must confirm the stop: {real['stops'][0]}", ("BHMS-CMP-050",))
