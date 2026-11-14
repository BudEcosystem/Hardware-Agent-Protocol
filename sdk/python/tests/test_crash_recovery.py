"""Crash windows with a real server process killed by SIGKILL and restarted on the same SQLite store.

Each test drives tests/helpers/crash_server.py over a Unix socket, freezes it at an exact point (SIGSTOP from inside,
see the helper), kills it with SIGKILL, restarts it, and checks the honest outcome of §6.9 / BHMS-OPS-080 / PRG-017.
The device side is a fsynced command log in the state directory, so "the device acted" is an observable fact.

Requirement IDs: BHMS-OPS-003, OPS-004, OPS-005, OPS-030, OPS-034, OPS-042, OPS-063, OPS-080, OPS-081, PRG-017.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from bhms.client.client import Client
from bhms.protocol.errors import BhmsError

HELPER = Path(__file__).parent / "helpers" / "crash_server.py"


class Proc:
    def __init__(self, state_dir: Path, sock: Path, **env: str) -> None:
        for marker in ("ready", "paused", "running"):
            (state_dir / marker).unlink(missing_ok=True)
        self.state_dir, self.sock = state_dir, sock
        environment = {**os.environ, **env}
        self.proc = subprocess.Popen([sys.executable, str(HELPER), str(state_dir), str(sock)], env=environment,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    async def ready(self, timeout: float = 20.0) -> None:
        await self.wait_for("ready", timeout)

    async def wait_for(self, marker: str, timeout: float = 20.0) -> None:
        deadline = time.monotonic() + timeout
        while not (self.state_dir / marker).exists():
            if self.proc.poll() is not None:
                raise RuntimeError(f"server exited: {self.proc.stderr.read().decode()[-2000:]}")
            if time.monotonic() > deadline:
                raise TimeoutError(marker)
            await asyncio.sleep(0.02)

    def kill(self) -> None:
        self.proc.send_signal(signal.SIGKILL)
        self.proc.wait(10)
        self.proc.stderr.close()

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(10)
        self.proc.stderr.close()


@pytest.fixture
def paths(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    return state, tmp_path / "crash.sock"


def device_log(state: Path) -> list[str]:
    path = state / "device.log"
    return path.read_text().splitlines() if path.exists() else []


async def start(state: Path, sock: Path, **env: str) -> tuple[Proc, Client]:
    proc = Proc(state, sock, **env)
    await proc.ready()
    return proc, await Client.connect(f"unix:{sock}", timeout=10)


async def crash_during_invoke(state: Path, sock: Path, marker: str, *, key: str, **env: str) -> None:
    """Invoke `move` under `key`, wait until the server reached `marker`, SIGKILL it."""
    proc, client = await start(state, sock, **env)
    request = asyncio.ensure_future(client.actions_invoke("arm-1", "move", {"x": 42}, operation_key=key,
                                                          wait_ms=30_000))
    await proc.wait_for(marker)
    proc.kill()
    with pytest.raises(Exception):  # noqa: B017 - the connection drops: TransportClosed
        await request
    await client.close()


async def replay(client: Client, key: str, device: str = "arm-1"):
    """Retry with the same key and intent: the stored operation comes back, nothing is re-sent."""
    res = await client.actions_invoke(device, "move", {"x": 42}, operation_key=key)
    assert res.replayed is True
    return (await client.operations_get(res.operation.operation_id)).operation


async def test_crash_after_dispatch_becomes_unknown(paths):  # BHMS-OPS-080, OPS-004, OPS-081 (Review Focus 1)
    state, sock = paths
    await crash_during_invoke(state, sock, "running", key="k-run", HANG="1", RECONCILE="0")
    assert device_log(state)[0].startswith("start ")  # the device acted (began moving)
    proc, client = await start(state, sock, RECONCILE="0")
    try:
        # the first answer after the restart is already honest; a conflicting request is refused (BHMS-OPS-042)
        with pytest.raises(BhmsError) as info:
            await client.actions_invoke("arm-1", "move", {"x": 1}, operation_key="k-other")
        op = await replay(client, "k-run")
        assert info.value.bhms_code == "STALE" and info.value.operation_id == op.operation_id
        assert op.state == "unknown" and op.effect == "unknown"
        assert (op.error.bhms_code, op.error.may_have_acted, op.error.retry) == ("DEADLINE_EXCEEDED", True,
                                                                                 "after-reconcile")
        assert "restarted" in op.error.message
        assert [h.state for h in op.history if h.kind == "state"] == ["accepted", "dispatching", "unknown"]
        assert len(device_log(state)) == 1  # BHMS-OPS-081: nothing was re-sent
    finally:
        await client.close()
        proc.stop()
    proc, client = await start(state, sock, RECONCILE="1")  # reconciliation from the device log
    try:
        op = await replay(client, "k-run")
        assert op.state == "failed" and op.error.may_have_acted is True
        assert op.history[-1].kind == "reconciliation" and "started but not finished" in op.history[-1].detail
        assert any(h.state == "unknown" for h in op.history)  # BHMS-OPS-005: the unknown entry remains
        ok = (await client.actions_invoke("arm-1", "move", {"x": 1}, operation_key="k-next", wait_ms=5000)).operation
        assert ok.state == "completed"
    finally:
        await client.close()
        proc.stop()


async def test_crash_after_intent_commit_before_handler_start(paths):  # §6.9 row 3, BHMS-OPS-003
    state, sock = paths
    await crash_during_invoke(state, sock, "paused", key="k-a", CRASH_PAUSE="before-start", RECONCILE="0")
    assert device_log(state) == []  # the handler never ran
    proc, client = await start(state, sock, RECONCILE="0")
    try:
        op = await replay(client, "k-a")
        # dispatching was durable, so the server cannot prove nothing was sent: unknown, never failed-no-effect
        assert op.state == "unknown" and op.error.may_have_acted is True
    finally:
        await client.close()
        proc.stop()
    proc, client = await start(state, sock, RECONCILE="1")
    try:
        op = await replay(client, "k-a")
        assert op.state == "failed" and op.error.may_have_acted is False and op.effect == "none"
        assert op.history[-1].kind == "reconciliation" and "no record" in op.history[-1].detail
        assert device_log(state) == []
    finally:
        await client.close()
        proc.stop()


async def test_crash_after_handler_returned_before_result_recorded(paths):  # §6.9 row 4
    state, sock = paths
    await crash_during_invoke(state, sock, "paused", key="k-c", CRASH_PAUSE="before-settle", RECONCILE="0")
    assert [line.split()[0] for line in device_log(state)] == ["start", "done"]  # the device finished
    proc, client = await start(state, sock, RECONCILE="0")
    try:
        op = await replay(client, "k-c")
        assert op.state == "unknown" and "result" not in op.model_fields_set  # never completed without evidence
    finally:
        await client.close()
        proc.stop()
    proc, client = await start(state, sock, RECONCILE="1")
    try:
        op = await replay(client, "k-c")
        assert op.state == "completed" and op.result == {"x": 42} and op.history[-1].kind == "reconciliation"
        assert len(device_log(state)) == 2  # never re-sent
    finally:
        await client.close()
        proc.stop()


async def test_crash_with_a_queued_operation_rejects_it(paths):  # §6.9 row 2, BHMS-OPS-080
    state, sock = paths
    proc, client = await start(state, sock, HANG="1", RECONCILE="0")
    first = (await client.actions_invoke("arm-1", "move", {"x": 1}, operation_key="busy")).operation
    await proc.wait_for("running")
    queued = (await client.actions_invoke("arm-1", "move", {"x": 2}, operation_key="queued")).operation
    assert queued.state == "accepted"
    proc.kill()
    await client.close()
    proc, client = await start(state, sock, RECONCILE="0")
    try:
        got = (await client.operations_get(queued.operation_id)).operation
        assert got.state == "rejected" and got.error.may_have_acted is False and got.effect == "none"
        assert (await client.operations_get(first.operation_id)).operation.state == "unknown"
        assert all(queued.operation_id not in line for line in device_log(state))
    finally:
        await client.close()
        proc.stop()


async def test_completed_result_survives_restart_with_same_epoch(paths):  # BHMS-OPS-034, OPS-063, §6.9 row 5
    state, sock = paths
    proc, client = await start(state, sock)
    epoch = client.server.epoch
    op = (await client.actions_invoke("arm-1", "move", {"x": 42}, operation_key="k-done", wait_ms=5000)).operation
    assert op.state == "completed"
    proc.kill()
    await client.close()
    proc, client = await start(state, sock)
    try:
        assert client.server.epoch == epoch
        again = await replay(client, "k-done")
        assert again.state == "completed" and again.operation_id == op.operation_id
        assert len(device_log(state)) == 2
    finally:
        await client.close()
        proc.stop()


async def crash_in_batch(state: Path, sock: Path, devices: int) -> tuple[list[str], list[str]]:
    """Group commit: invoke ``move`` on ``devices`` devices at once under keys b-1..b-N; the first intent's fsync is slow,
    the rest pile up behind it, and the process is SIGKILLed before the fsync covering that batch runs. Returns the keys
    whose invoke was answered and those whose connection dropped first."""
    proc, client = await start(state, sock, CRASH_PAUSE="in-batch", DEVICES=str(devices), RECONCILE="0")
    keys = [f"b-{i}" for i in range(1, devices + 1)]
    requests = {key: asyncio.ensure_future(client.actions_invoke(f"arm-{i}", "move", {"x": 42}, operation_key=key,
                                                                 wait_ms=30_000))
                for i, key in enumerate(keys, start=1)}
    await proc.wait_for("paused")
    proc.kill()
    answered, dropped = [], []
    for key, request in requests.items():
        try:
            await request
            answered.append(key)
        except Exception:  # noqa: BLE001 - TransportClosed: no answer
            dropped.append(key)
    await client.close()
    return answered, dropped


def acted(state: Path) -> dict[str, str]:
    """What the device log says each operation did: ``done``, or ``start`` when it began and never finished."""
    out: dict[str, str] = {}
    for line in device_log(state):
        word, op_id = line.split()
        out[op_id] = "done" if word == "done" or out.get(op_id) == "done" else word
    return out


def check_reconciled(op, log: dict[str, str]) -> None:
    """The outcome a reconciliation from the device log must give (see helpers/crash_server.py)."""
    if log.get(op.operation_id) == "done":
        assert op.state == "completed"
    elif log.get(op.operation_id) == "start":
        assert op.state == "failed" and op.error.may_have_acted is True
    else:  # its intent was written but no handler ever ran
        assert op.state == "failed" and op.effect == "none" and op.error.may_have_acted is False


async def test_kill_during_a_group_commit_batch_recovers_honestly(paths):  # BHMS-OPS-003, OPS-080, OPS-081 (Task 12b)
    state, sock = paths
    answered, dropped = await crash_in_batch(state, sock, devices=5)
    log = acted(state)
    assert len(log) <= 1 and len(dropped) >= 4  # at most the intent the completed fsync covered reached a device
    proc, client = await start(state, sock, DEVICES="5", RECONCILE="0")
    try:
        ops = {key: await replay(client, key, f"arm-{key[2:]}") for key in answered + dropped}  # SIGKILL keeps commits
        assert len(ops) == 5
        for op in ops.values():
            assert op.state == ("completed" if log.get(op.operation_id) == "done" else "unknown")
            if op.state == "unknown":
                assert op.error.may_have_acted is True  # the server cannot vouch for what it did not see
    finally:
        await client.close()
        proc.stop()
    proc, client = await start(state, sock, DEVICES="5", RECONCILE="1")
    try:
        for key in answered + dropped:
            check_reconciled(await replay(client, key, f"arm-{key[2:]}"), log)
        assert acted(state) == log  # nothing was re-sent
    finally:
        await client.close()
        proc.stop()


async def test_power_loss_during_a_group_commit_batch_loses_only_unanswered_intents(paths):  # BHMS-OPS-003 (Task 12b)
    """As above, but what a power loss would keep: the WAL is cut back to its size when the completed fsync began (and the
    shared-memory index, which lives in RAM, is gone). The one intent that fsync covered survives (its completion may
    not); the intents of the lost batch vanish, none of them was answered or reached a device, and a retry with the same
    key runs each exactly once."""
    state, sock = paths
    answered, dropped = await crash_in_batch(state, sock, devices=5)
    log = acted(state)
    assert len(log) <= 1 and len(dropped) >= 4
    db = state / "crash-server.sqlite3"
    os.truncate(f"{db}-wal", int((state / "durable_wal_size").read_text()))
    Path(f"{db}-shm").unlink(missing_ok=True)
    proc, client = await start(state, sock, DEVICES="5", RECONCILE="1")
    try:
        survivors = []
        for i in range(1, 6):
            key = f"b-{i}"
            res = await client.actions_invoke(f"arm-{i}", "move", {"x": 42}, operation_key=key, wait_ms=10_000)
            if res.replayed:  # its intent was durable before its handler could run
                survivors.append(key)
                check_reconciled(res.operation, log)
            else:  # lost with the batch: it had not been answered and no device had seen it
                assert key in dropped and res.operation.state == "completed"
        assert len(survivors) == 1
        starts = [line.split()[1] for line in device_log(state) if line.startswith("start")]
        assert len(starts) == len(set(starts)) == len(log) + 4  # each intent acted at most once
    finally:
        await client.close()
        proc.stop()


PROGRAM = {
    "bhmsProgram": "2026-11-13", "name": "move_then_wait", "description": "Move, then wait.",
    "input": {"type": "object", "additionalProperties": False, "properties": {}},
    "maxDurationMs": 3_600_000,
    "steps": [{"kind": "invoke", "deviceId": "arm-1", "action": "move", "arguments": {"x": 5}},
              {"kind": "sleep", "durationMs": 600_000},
              {"kind": "invoke", "deviceId": "arm-1", "action": "move", "arguments": {"x": 6}}],
}


async def test_crash_between_program_steps_fails_the_program(paths):  # BHMS-PRG-017
    state, sock = paths
    proc, client = await start(state, sock)
    op = (await client.programs_run(program=PROGRAM, arguments={}, operation_key="p-1")).operation
    for _ in range(200):
        if (await client.operations_get(op.operation_id)).operation.progress.steps_completed >= 1:
            break
        await asyncio.sleep(0.02)
    proc.kill()
    await client.close()
    proc, client = await start(state, sock)
    try:
        got = (await client.operations_get(op.operation_id)).operation
        assert got.state == "failed" and got.error.bhms_code == "INTERNAL" and got.error.may_have_acted is True
        assert got.error.message == "server restarted during the program" and "stepIndex 0" in got.error.hint
        assert len([line for line in device_log(state) if line.startswith("start")]) == 1  # never resumed
    finally:
        await client.close()
        proc.stop()


async def test_crash_during_a_program_step_is_unknown_until_the_child_is_reconciled(paths):  # BHMS-PRG-017
    state, sock = paths
    proc, client = await start(state, sock, HANG="1", RECONCILE="0")
    op = (await client.programs_run(program=PROGRAM, arguments={}, operation_key="p-2")).operation
    await proc.wait_for("running")
    proc.kill()
    await client.close()
    proc, client = await start(state, sock, RECONCILE="0")
    try:
        got = (await client.operations_get(op.operation_id)).operation
        assert got.state == "unknown" and got.error.bhms_code == "DEADLINE_EXCEEDED"
    finally:
        await client.close()
        proc.stop()
    proc, client = await start(state, sock, RECONCILE="1")
    try:
        got = (await client.operations_get(op.operation_id)).operation
        assert got.state == "failed" and got.error.message == "server restarted during the program"
        assert got.history[-1].kind == "reconciliation"
    finally:
        await client.close()
        proc.stop()
