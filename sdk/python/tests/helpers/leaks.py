"""What a test may not leave behind: pending asyncio tasks and open subprocess transports (Task 7b, A6).

A leaked ``bhms-session-reader`` task or stdio subprocess transport is destroyed by the garbage collector during some
later test and, under ``-W error``, fails *that* test. :class:`LeakWatch` lets ``tests/conftest.py`` fail the test that
leaked instead, by name. It tracks every subprocess transport asyncio creates (a weak set filled by a wrapper around
``BaseSubprocessTransport.__init__``) and reads the running loop's tasks.
"""

from __future__ import annotations

import asyncio
import weakref
from asyncio import base_subprocess
from typing import Any

Transport = base_subprocess.BaseSubprocessTransport


class LeakWatch:
    """Tracks subprocess transports for a session; one instance is installed at a time."""

    def __init__(self) -> None:
        self._live: weakref.WeakSet[Transport] = weakref.WeakSet()
        self._original: Any = None

    @classmethod
    def install(cls) -> LeakWatch:
        watch = cls()
        watch._original = original = Transport.__init__
        live = watch._live

        def tracked(self: Transport, *args: Any, **kwargs: Any) -> None:
            original(self, *args, **kwargs)
            live.add(self)

        Transport.__init__ = tracked  # type: ignore[method-assign]
        return watch

    def uninstall(self) -> None:
        Transport.__init__ = self._original  # type: ignore[method-assign]

    def baseline(self) -> set[Transport]:
        """The transports that already exist (owned by session-scoped fixtures or earlier, already reported, tests)."""
        return set(self._live)

    def _leaked(self, baseline: set[Transport]) -> tuple[list[asyncio.Task[Any]], list[Transport]]:
        me = asyncio.current_task()
        tasks = [t for t in asyncio.all_tasks() if t is not me and not t.done()]
        procs = [p for p in set(self._live) - baseline if not p._closed or p._returncode is None]
        return tasks, procs

    async def leaked_after(self, baseline: set[Transport], *, grace_s: float) -> tuple[list[asyncio.Task[Any]], list[Transport]]:
        """Tasks still pending and subprocess transports still open (or their child unreaped) after ``grace_s``: the time
        a task that is already ending (cancelled, or on its last await) and a killed child get to finish."""
        deadline = asyncio.get_running_loop().time() + grace_s
        tasks, procs = self._leaked(baseline)
        while (tasks or procs) and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
            tasks, procs = self._leaked(baseline)
        return tasks, procs

    @staticmethod
    def describe(tasks: list[asyncio.Task[Any]], procs: list[Transport]) -> str:
        parts = []
        if tasks:
            names = sorted(f"{t.get_name()} ({getattr(t.get_coro(), '__qualname__', t.get_coro())})" for t in tasks)
            parts.append(f"asyncio tasks still running: {names}")
        if procs:
            parts.append(f"subprocess transports still open: {sorted(f'pid {p.get_pid()}' for p in procs)}")
        return "the test left " + " and ".join(parts)

    @staticmethod
    async def reap(tasks: list[asyncio.Task[Any]], procs: list[Transport]) -> None:
        """End what was found so that the next test starts clean."""
        for task in tasks:
            task.cancel()
        waiters = [asyncio.ensure_future(p._wait()) for p in procs if p._returncode is None]
        for proc in procs:
            proc.close()  # closes the pipes and kills a child that is still running
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if waiters:
            await asyncio.wait(waiters, timeout=10)
