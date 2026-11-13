"""Gateway step 5: isolation, backpressure, upstream crash -> unknown -> reconciliation (real upstream processes).

Spec: BHMS-SEC-061 (test_stalled_server_isolated), OPS-004/005/042/080/081, 14-conformance fault rows.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sqlite3
import sys
import time
from pathlib import Path

import pytest

from bhms.client.client import Client
from bhms.gateway import Gateway, GatewayConfig, UpstreamConfig
from bhms.protocol.errors import BhmsError
from helpers.gateway_rig import principals, rig

HELPER = Path(__file__).parent / "helpers" / "gateway_upstream.py"


def stdio_upstream(name: str, state: Path, *, env: dict[str, str] | None = None, **kw) -> UpstreamConfig:
    return UpstreamConfig(name=name, stdio=f"{sys.executable} {HELPER} {state}", health_interval_ms=300,
                          health_timeout_ms=500, env=env or {}, **kw)


def device_log(state: Path) -> list[str]:
    path = state / "device.log"
    return path.read_text().splitlines() if path.exists() else []


def upstream_ops(state: Path, name: str = "gw-upstream") -> list[tuple[str, str]]:
    db = sqlite3.connect(f"file:{state / (name + '.sqlite3')}?mode=ro", uri=True)
    try:
        return [(r[0], r[1]) for r in db.execute("SELECT op_key, state FROM operations ORDER BY created_ns")]
    finally:
        db.close()


def child_pid(gateway: Gateway, name: str) -> int:
    return gateway.upstreams[name].client.session._transport.process.pid


async def start_gateway(tmp_path, upstreams, **kw) -> tuple[Gateway, Client]:
    config = GatewayConfig(id="gw-iso", state_dir=tmp_path / "gw", upstreams=tuple(upstreams),
                           principals=principals(agent_scopes=["read", "lease", "stop", "invoke:*/*"]), connect_wait_ms=15000, **kw)
    gateway = Gateway(config)
    await gateway.start()
    await gateway.listen(f"unix:{tmp_path}/gw.sock")
    return gateway, await Client.connect(f"unix:{tmp_path}/gw.sock")


async def stop_gateway(gateway: Gateway, client: Client) -> None:
    await client.close()
    await gateway.close()


async def until(predicate, timeout=20.0, step=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = await predicate()
        if found:
            return found
        await asyncio.sleep(step)
    raise AssertionError("condition not reached in time")


async def test_upstream_killed_mid_operation_becomes_unknown_then_reconciles(tmp_path):  # OPS-004, 005, 080
    state = tmp_path / "up"
    gateway, client = await start_gateway(tmp_path, [stdio_upstream("dev", state)])
    try:
        op = (await client.actions_invoke("dev/axis-1", "hold", {}, operation_key="mid")).operation
        await until(lambda: asyncio.sleep(0, any(line.startswith("start") for line in device_log(state))))
        old_pid = child_pid(gateway, "dev")
        os.kill(old_pid, signal.SIGKILL)
        got = await until(lambda: _state_is(client, op.operation_id, "unknown"))
        assert got.error.bhms_code == "DEADLINE_EXCEEDED" and got.error.may_have_acted is True
        assert got.error.retry == "after-reconcile" and got.effect == "unknown"
        listing = (await client.devices_list()).devices
        assert listing[0].status == "offline"
        with pytest.raises(BhmsError) as exc:  # nothing new goes to a dead upstream
            await client.actions_invoke("dev/axis-1", "move", {"x": 1}, operation_key="new")
        assert exc.value.code == "DEVICE_UNAVAILABLE" and exc.value.may_have_acted is False
        # the gateway restarts the upstream; its durable journal recovers the operation as unknown and its reconcile
        # hook answers from the device log; the gateway records that as a reconciliation
        settled = await until(lambda: _state_is(client, op.operation_id, "failed"), timeout=30)
        assert settled.error.may_have_acted is True
        history = (await client.operations_get(op.operation_id)).operation.history
        assert [h.kind for h in history if h.state == "failed"] == ["reconciliation"]
        assert any(h.state == "unknown" for h in history)  # the unknown entry stays in the history (OPS-005)
        assert child_pid(gateway, "dev") != old_pid
        ops = upstream_ops(state)
        assert len(ops) == 1 and ops[0][1] == "failed"  # one operation upstream: never re-sent, never run twice
        assert sum(line.startswith("start") for line in device_log(state)) == 1
        listing = await until(lambda: _online(client))
        assert listing
    finally:
        await stop_gateway(gateway, client)


async def _state_is(client, op_id, state):
    got = (await client.operations_get(op_id)).operation
    return got if got.state == state else None


async def _online(client):
    return all(d.status == "online" for d in (await client.devices_list()).devices)


async def test_unknown_inhibits_the_resources_across_a_reconnect(tmp_path):  # BHMS-OPS-042
    state = tmp_path / "up"
    gateway, client = await start_gateway(tmp_path, [stdio_upstream("dev", state, env={"RECONCILE": "0"})])
    try:
        op = (await client.actions_invoke("dev/axis-1", "hold", {}, operation_key="mid")).operation
        await until(lambda: asyncio.sleep(0, any(line.startswith("start") for line in device_log(state))))
        os.kill(child_pid(gateway, "dev"), signal.SIGKILL)
        await until(lambda: _state_is(client, op.operation_id, "unknown"))
        await until(lambda: _online(client), timeout=30)  # the upstream is back; the outcome is still unknown
        with pytest.raises(BhmsError) as exc:
            await client.actions_invoke("dev/axis-1", "move", {"x": 1}, operation_key="blocked")
        assert exc.value.code == "STALE" and exc.value.operation_id == op.operation_id
        assert "isolation:unknown-operation" in exc.value.hint
        assert (await client.operations_get(op.operation_id)).operation.state == "unknown"
        # a confirmed stop of the device lifts it (BHMS-OPS-042); the outcome itself stays unknown
        stops = (await client.stop("test", device_ids=["dev/axis-1"], wait_ms=2000)).stops
        assert stops[0].outcome == "confirmed" and stops[0].evidence == "reported"
        again = await client.actions_invoke("dev/axis-1", "move", {"x": 1}, operation_key="free", wait_ms=2000)
        assert again.operation.state == "completed"
        assert (await client.operations_get(op.operation_id)).operation.state == "unknown"
    finally:
        await stop_gateway(gateway, client)


async def test_epoch_change_is_never_reconciled_by_resending(tmp_path):  # BHMS-OPS-081, OPS-034
    state = tmp_path / "up"
    gateway, client = await start_gateway(tmp_path, [stdio_upstream("dev", state, env={"MEMORY": "1"})])
    try:
        op = (await client.actions_invoke("dev/axis-1", "hold", {}, operation_key="mid")).operation
        await until(lambda: asyncio.sleep(0, any(line.startswith("start") for line in device_log(state))))
        old_epoch = gateway.upstreams["dev"].epoch
        os.kill(child_pid(gateway, "dev"), signal.SIGKILL)
        await until(lambda: _state_is(client, op.operation_id, "unknown"))
        await until(lambda: _online(client), timeout=30)
        assert gateway.upstreams["dev"].epoch != old_epoch  # a new epoch: its journal is gone
        got = await until(lambda: _unreconcilable(gateway, op.operation_id))
        assert got.state == "unknown"
        history = (await client.operations_get(op.operation_id)).operation.history
        assert any(h.kind == "correction" and "cannot be reconciled" in (h.detail or "") for h in history)
        assert sum(line.startswith("start") for line in device_log(state)) == 1  # never executed again
    finally:
        await stop_gateway(gateway, client)


async def _unreconcilable(gateway, op_id):
    rec = gateway.journal.get(op_id)
    return rec if rec.private.get("unreconcilable") else None


async def test_stalled_server_isolated(tmp_path):  # BHMS-SEC-061
    stalled, healthy = tmp_path / "stalled", tmp_path / "healthy"
    gateway, client = await start_gateway(tmp_path, [stdio_upstream("slow", stalled), stdio_upstream("fast", healthy)])
    try:
        op = (await client.actions_invoke("slow/axis-1", "hold", {}, operation_key="held")).operation
        await until(lambda: asyncio.sleep(0, any(line.startswith("start") for line in device_log(stalled))))

        async def fast_latency(n=20) -> float:
            started = time.perf_counter()
            for i in range(n):
                await client.actions_invoke("fast/axis-1", "move", {"x": i}, operation_key=f"f{time.monotonic()}-{i}",
                                            wait_ms=2000)
            return (time.perf_counter() - started) / n

        baseline = await fast_latency()
        pid = child_pid(gateway, "slow")
        os.kill(pid, signal.SIGSTOP)  # the process stops answering without closing anything
        try:
            during = []
            blocked = asyncio.create_task(client.properties_read("slow/axis-1", "position", fresh=True))
            for _ in range(10):
                during.append(await fast_latency(5))
            assert max(during) < baseline * 5 + 0.05  # the healthy upstream's latency is unaffected
            statuses = await until(lambda: _statuses(client, "slow/axis-1", "offline"), timeout=10)
            assert statuses["fast/axis-1"] == "online"
            started = time.perf_counter()
            with pytest.raises(BhmsError) as exc:  # fails fast now, it does not queue behind a dead peer
                await client.actions_invoke("slow/axis-1", "move", {"x": 1}, operation_key="to-stalled")
            assert exc.value.code == "DEVICE_UNAVAILABLE" and exc.value.may_have_acted is False
            assert time.perf_counter() - started < 0.2
            got = await until(lambda: _state_is(client, op.operation_id, "unknown"), timeout=10)
            assert got.error.may_have_acted is True  # in flight when the link stalled
            with contextlib.suppress(BhmsError):
                await asyncio.wait_for(blocked, 15)
        finally:
            os.kill(pid, signal.SIGCONT)
        await until(lambda: _statuses(client, "slow/axis-1", "online"), timeout=15)
        (stalled / "release").write_text("go")
        settled = await until(lambda: _state_is(client, op.operation_id, "completed"), timeout=15)
        assert settled.state == "completed"
    finally:
        await stop_gateway(gateway, client)


async def _statuses(client, device, status):
    found = {d.device_id: d.status for d in (await client.devices_list()).devices}
    return found if found[device] == status else None


async def test_bounded_queue_refuses_with_busy_and_others_are_unaffected(tmp_path):  # BHMS-SEC-061
    async with rig(tmp_path, conformance=True, upstream_kw={"max_inflight": 1, "queue_size": 1}) as r:
        client = await r.client()
        direct = await Client.connect(f"unix:{tmp_path}/a.sock")  # another path to upstream a holds every resource
        try:
            await direct.leases_acquire(["axis-1/clamp", "axis-1/motion", "pump-1/plunger"], 20000)
            started = time.perf_counter()
            calls = [asyncio.create_task(client.leases_acquire([res], 5000, wait_ms=1200))
                     for res in ("a/axis-1/clamp", "a/axis-1/motion", "a/pump-1/plunger")]  # each blocks upstream
            await asyncio.sleep(0.3)
            assert (await client.properties_read("b/axis-1", "position")).observation.quality == "valid"
            assert time.perf_counter() - started < 1.0  # the other upstream is not held up by the saturated one
            results = await asyncio.gather(*calls, return_exceptions=True)
            assert all(isinstance(x, BhmsError) for x in results)
            assert sorted(x.code for x in results) == ["BUSY", "LEASE_CONFLICT", "LEASE_CONFLICT"]  # 1 running, 1 queued
            busy = next(x for x in results if x.code == "BUSY")
            assert busy.may_have_acted is False and "isolation:queue-bounded" in busy.hint
            assert r.gateway.leases.manager.active() == []  # nothing was left held by the refused attempts
        finally:
            await direct.close()
