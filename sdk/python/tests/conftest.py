"""Suite-wide guard: no test may leave files in the directory pytest runs from (fixtures use ``tmp_path``)."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _no_files_left_in_cwd():
    before = set(os.listdir("."))
    yield
    left = sorted(set(os.listdir(".")) - before - {".pytest_cache", "__pycache__", ".ruff_cache"})
    assert not left, f"the test left files in the working directory: {left}"


@pytest.fixture(scope="session")
def native(tmp_path_factory):
    """The sdk/c host simulators (``sim_device``, ``sim_bench``), built once with cmake; the test is skipped without a toolchain."""
    from bhms.testing.compact_endpoint import NativeUnavailable, build_native

    try:
        return build_native(tmp_path_factory.mktemp("sdk-c-build"))
    except NativeUnavailable as exc:
        pytest.skip(str(exc))
