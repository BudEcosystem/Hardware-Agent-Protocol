"""A barrier whose sync fails after its commit leaves no zombie (Task 12b review, carried to Task 15a).

* The program create barrier fails and the ``rejected`` transition that should follow fails too: the caller is refused
  ``BUSY`` instead of being handed a still-``accepted`` program that nothing will ever run.
* A synchronous ``dispatching`` barrier (a program's first step, a gateway's mirror, recovery) that is committed but not
  durable: memory and the database agree, and a program that started nothing ends ``failed`` with ``mayHaveActed: false``.
"""

from __future__ import annotations

import errno
import os

import pytest

from bhms.protocol.errors import BhmsError
from bhms.runtime import store as store_module
from bhms.runtime.operations import Journal
from bhms.runtime.store import Store, StoreError, StoreSyncError
from bhms.server import DeviceServer, Range
from bhms.testing.harness import connect


class FailingSync:
    def __init__(self) -> None:
        self.fail = False

    def __call__(self, fd: int) -> None:
        if self.fail:
            raise OSError(errno.EIO, "Input/output error")
        os.fsync(fd)


def server(tmp_path) -> DeviceServer:
    srv = DeviceServer("sync-failures", state_dir=tmp_path / "state")
    dev = srv.device("d", resources=["d"])
    dev.report_alive()

    @dev.action(effect="reversible", idempotency="absolute", max_duration_ms=5000)
    async def go(ctx, value: Range(0, 10, unit="1")) -> None:  # noqa: F821
        """Go."""

    return srv


PROGRAM = {"bhmsProgram": "2026-11-15", "name": "p", "description": "p", "maxDurationMs": 10_000,
           "input": {"type": "object", "additionalProperties": False, "properties": {}},
           "steps": [{"kind": "invoke", "deviceId": "d", "action": "go", "arguments": {"value": 1}}]}


async def test_a_program_whose_create_sync_and_rejection_both_fail_is_refused_busy(tmp_path, monkeypatch):
    sync = FailingSync()
    monkeypatch.setattr(store_module.os, "fdatasync", sync)
    async with connect(server(tmp_path), strict=False) as client:
        sync.fail = True
        original = Journal.transition

        def refuse_rejection(self, rec, state, **kw):
            if state == "rejected":
                raise StoreError("journal write failed: disk I/O error")
            return original(self, rec, state, **kw)

        monkeypatch.setattr(Journal, "transition", refuse_rejection)
        with pytest.raises(BhmsError) as exc:
            await client.programs_run(program=PROGRAM, arguments={}, operation_key="zombie", wait_ms=1000)
        assert exc.value.bhms_code == "BUSY" and exc.value.may_have_acted is False


async def test_a_dispatching_barrier_that_is_not_durable_leaves_memory_and_journal_in_agreement(tmp_path, monkeypatch):
    sync = FailingSync()
    monkeypatch.setattr(store_module.os, "fdatasync", sync)
    store = Store(tmp_path / "j.sqlite3")
    try:
        journal = Journal(store)
        rec = journal.create(principal="p", key="k", key_origin="client", kind="program", request_digest="sha256:" + "0" * 64,
                             arguments={}, private={"effectClass": "reversible"}, program_digest="sha256:" + "1" * 64,
                             barrier=False)
        sync.fail = True
        with pytest.raises(StoreSyncError):
            journal.transition(rec, "dispatching")
        assert rec.state == "dispatching" == store.get_operation(rec.id).record["state"]  # no zombie accepted
    finally:
        store.close()


async def test_a_program_whose_first_step_barrier_is_not_durable_ends_failed_with_nothing_sent(tmp_path, monkeypatch):
    sync = FailingSync()
    monkeypatch.setattr(store_module.os, "fdatasync", sync)
    srv = server(tmp_path)
    async with connect(srv, strict=False) as client:
        original = Journal.transition

        def fail_sync_on_program_dispatch(self, rec, state, **kw):
            if state == "dispatching" and rec.op["kind"] == "program":
                sync.fail = True
            return original(self, rec, state, **kw)

        monkeypatch.setattr(Journal, "transition", fail_sync_on_program_dispatch)
        op = (await client.programs_run(program=PROGRAM, arguments={}, operation_key="first-step",
                                        wait_ms=3000)).operation
        assert op.state == "failed" and op.error.may_have_acted is False and op.effect == "none", op
        assert srv.journal.children(op.operation_id) == []  # no step was admitted
