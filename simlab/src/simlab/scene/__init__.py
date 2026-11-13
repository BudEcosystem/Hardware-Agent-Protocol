"""Scene files and the default arm model lookup."""

from __future__ import annotations

import os
from pathlib import Path

BENCH = Path(__file__).with_name("bench.xml")


def default_arm_model() -> Path:
    """The Menagerie SO-ARM100 MJCF, found in the ``robot_descriptions`` cache without importing that package.

    ``robot_descriptions`` clones from GitHub on import, which is not wanted on a metered link; the cache layout is
    stable, so the file is located directly. Override with ``SIMLAB_ARM_MODEL`` (the BHMS arm MJCF, Task 13) or pass
    ``arm_model=`` to :class:`simlab.world.World`.
    """
    override = os.environ.get("SIMLAB_ARM_MODEL")
    if override:
        return Path(override)
    cache = Path(os.environ.get("ROBOT_DESCRIPTIONS_CACHE", Path.home() / ".cache" / "robot_descriptions"))
    path = cache / "mujoco_menagerie" / "trs_so_arm100" / "so_arm100.xml"
    if not path.is_file():
        raise FileNotFoundError(f"SO-ARM100 model not found at {path}; set ROBOT_DESCRIPTIONS_CACHE or SIMLAB_ARM_MODEL")
    return path
