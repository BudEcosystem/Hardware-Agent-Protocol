"""Suite-wide guards.

* No test may leave files in the directory pytest runs from (fixtures use ``tmp_path``).
* No test may leave an asyncio task or a subprocess transport behind (Task 7b, A6): a leaked ``bhms-session-reader`` task or
  stdio subprocess transport is garbage-collected during some later test and, under ``-W error``, fails *that* test. The
  guard fails the test that leaked, by name.
"""

from __future__ import annotations

import asyncio
import os
import weakref
from asyncio import base_subprocess

import pytest

_GRACE_S = 1.0
"""How long a task that is already finishing (cancelled, or on its last await) gets to end before it counts as leaked."""


@pytest.fixture(autouse=True)
def _no_files_left_in_cwd():
    before = set(os.listdir("."))
    yield
    left = sorted(set(os.listdir(".")) - before - {".pytest_cache", "__pycache__", ".ruff_cache"})
    assert not left, f"the test left files in the working directory: {left}"


@pytest.fixture(scope="session", autouse=True)
def _subprocess_transports():
    """Every subprocess transport asyncio creates during the session, weakly held (see :func:`_nothing_outlives_the_test`)."""
    live: weakref.WeakSet[base_subprocess.BaseSubprocessTransport] = weakref.WeakSet()
    original = base_subprocess.BaseSubprocessTransport.__init__

    def tracked(self, *args, **kwargs):
        original(self, *args, **kwargs)
        live.add(self)

    base_subprocess.BaseSubprocessTransport.__init__ = tracked
    try:
        yield live
    finally:
        base_subprocess.BaseSubprocessTransport.__init__ = original


def _describe(task: asyncio.Task) -> str:
    coro = task.get_coro()
    return f"{task.get_name()} ({getattr(coro, '__qualname__', coro)})"


@pytest.fixture(autouse=True)
async def _nothing_outlives_the_test(_subprocess_transports):
    """Fails the test that leaves a pending asyncio task or an open subprocess transport on its event loop.

    Set up first and torn down last (an autouse conftest fixture), so every other fixture has released its resources.
    """
    known = set(_subprocess_transports)
    yield
    me = asyncio.current_task()
    deadline = asyncio.get_running_loop().time() + _GRACE_S

    def leaked() -> tuple[list[asyncio.Task], list[base_subprocess.BaseSubprocessTransport]]:
        tasks = [t for t in asyncio.all_tasks() if t is not me and not t.done()]
        procs = [p for p in set(_subprocess_transports) - known if not p._closed or p._returncode is None]
        return tasks, procs

    tasks, procs = leaked()
    while (tasks or procs) and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.01)
        tasks, procs = leaked()
    for task in tasks:  # never leave them for the next test: cancel, then report
        task.cancel()
    for proc in procs:
        proc.close()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    assert not tasks, f"the test left asyncio tasks running: {sorted(_describe(t) for t in tasks)}"
    assert not procs, f"the test left subprocess transports open: {[f'pid {p.get_pid()}' for p in procs]}"
