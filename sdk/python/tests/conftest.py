"""Suite-wide guards.

* No test may leave files in the directory pytest runs from (fixtures use ``tmp_path``).
* No test may leave an asyncio task or a subprocess transport behind (Task 7b, A6; see ``helpers/leaks.py``): the guard
  fails the test that leaked, by name, instead of whichever later test the garbage collector happens to interrupt.
"""

from __future__ import annotations

import os

import pytest

from helpers.leaks import LeakWatch

_GRACE_S = 1.0
"""How long a task that is already finishing (cancelled, or on its last await) gets to end before it counts as leaked."""


@pytest.fixture(autouse=True)
def _no_files_left_in_cwd():
    before = set(os.listdir("."))
    yield
    left = sorted(set(os.listdir(".")) - before - {".pytest_cache", "__pycache__", ".ruff_cache"})
    assert not left, f"the test left files in the working directory: {left}"


@pytest.fixture(scope="session", autouse=True)
def _leak_watch():
    """Session-wide tracking of every subprocess transport asyncio creates (see :func:`_nothing_outlives_the_test`)."""
    watch = LeakWatch.install()
    try:
        yield watch
    finally:
        watch.uninstall()


@pytest.fixture(autouse=True)
async def _nothing_outlives_the_test(_leak_watch):
    """Fails the test that leaves a pending asyncio task or an open subprocess transport behind.

    Set up first and torn down last (an autouse conftest fixture), so every other fixture has released its resources.
    """
    baseline = _leak_watch.baseline()
    yield
    tasks, procs = await _leak_watch.leaked_after(baseline, grace_s=_GRACE_S)
    if tasks or procs:
        message = _leak_watch.describe(tasks, procs)
        await _leak_watch.reap(tasks, procs)
        pytest.fail(message)
