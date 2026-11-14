"""Task 7b A6: nothing a stdio connection owns outlives it, and the suite guard names the test that leaks.

The flake: a stdio subprocess transport and a pending ``bhms-session-reader`` task were garbage-collected during a later
test (``test_brief_example_description_is_schema_valid_with_stable_digest``), which then failed under ``-W error``.
"""

from __future__ import annotations

import asyncio
import gc
import sys
import warnings
from pathlib import Path

import pytest

from bhms.client.client import Client
from bhms.jsonrpc.session import Session
from bhms.transport.base import TransportClosed
from bhms.transport.stdio import spawn_stdio

HELPERS = Path(__file__).parent / "helpers"
SLOW_EXIT = f"{sys.executable} {HELPERS / 'slow_exit_stdio.py'}"
STDIO_SERVER = f"{sys.executable} {HELPERS / 'stdio_server.py'}"


def _released(process: asyncio.subprocess.Process) -> bool:
    """The event loop's transport of the child is closed (so its finaliser has nothing to warn about)."""
    transport = process._transport  # the asyncio object whose __del__ raises the ResourceWarning
    return transport is None or transport._closed


def _collect_without_warnings() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        gc.collect()


async def test_abort_releases_the_child_and_its_event_loop_transport():
    """``abort`` is what a session falls back to when ``close`` takes too long; it used to kill the child and leave the
    asyncio subprocess transport to the garbage collector."""
    transport = await spawn_stdio(SLOW_EXIT)
    process = transport.process
    transport.abort()
    assert _released(process)
    assert await asyncio.wait_for(process.wait(), 10) is not None  # killed, and reaped by the loop
    del transport, process
    _collect_without_warnings()


async def test_a_session_whose_transport_close_times_out_leaves_nothing_behind():
    """The child ignores EOF and SIGTERM; the session's flush timeout expires during ``close`` and it aborts."""
    transport = await spawn_stdio(SLOW_EXIT, grace_s=5.0)
    process = transport.process
    session = Session(transport, role="client", flush_timeout=0.2).start()
    reader = session._reader
    await session.close()
    assert _released(process)
    assert reader.done(), "the reader task must have ended with the session, not be left to the event loop"
    assert await asyncio.wait_for(process.wait(), 10) is not None
    del transport, process, session, reader
    _collect_without_warnings()


async def test_close_releases_the_transport_of_a_child_that_died_mid_session():
    client = await Client.connect(f"stdio:{STDIO_SERVER}")
    process = client.session._transport.process
    reader, writer = client.session._reader, client.session._writer
    process.kill()
    with pytest.raises(TransportClosed):
        await asyncio.wait_for(client.request("x-test/ping", {"n": 1}), 10)
    await client.close()
    assert _released(process) and process.returncode is not None
    assert reader.done() and writer.done()
    del client, process, reader, writer
    _collect_without_warnings()


async def test_a_graceful_close_releases_the_transport_too():
    client = await Client.connect(f"stdio:{STDIO_SERVER}")
    process = client.session._transport.process
    await client.close()
    assert process.returncode == 0 and _released(process)


# ---------------------------------------------------------------------------- the suite guard (tests/conftest.py)


async def test_the_guard_reports_a_pending_task_and_an_open_subprocess_transport():
    from helpers.leaks import LeakWatch

    watch = LeakWatch.install()
    try:
        baseline = watch.baseline()
        assert await watch.leaked_after(baseline, grace_s=0.05) == ([], [])

        async def forever():
            await asyncio.Event().wait()

        task = asyncio.create_task(forever(), name="bhms-session-reader")
        process = await asyncio.create_subprocess_exec(sys.executable, "-c", "import time; time.sleep(30)")
        tasks, procs = await watch.leaked_after(baseline, grace_s=0.05)
        assert [t.get_name() for t in tasks] == ["bhms-session-reader"] and [p.get_pid() for p in procs] == [process.pid]
        message = watch.describe(tasks, procs)
        assert "bhms-session-reader" in message and f"pid {process.pid}" in message
        await watch.reap(tasks, procs)  # the guard never leaves what it found for the next test
        assert task.cancelled() and await asyncio.wait_for(process.wait(), 10) is not None
        assert await watch.leaked_after(baseline, grace_s=0.05) == ([], [])
    finally:
        watch.uninstall()


async def test_the_guard_gives_a_finishing_task_its_grace():
    from helpers.leaks import LeakWatch

    watch = LeakWatch.install()
    try:
        baseline = watch.baseline()
        asyncio.get_running_loop().create_task(asyncio.sleep(0.05))
        assert await watch.leaked_after(baseline, grace_s=1.0) == ([], [])
    finally:
        watch.uninstall()
