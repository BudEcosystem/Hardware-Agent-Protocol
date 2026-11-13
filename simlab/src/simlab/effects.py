"""Effect kinds: which ones mark the start of an execution.

Every effect kind the world records is declared here as either an *execution start* (the device did something to the world:
moved, gripped, transferred liquid, changed a set-point, spun up) or an *observation or bookkeeping* record (a frame
captured, a plate read, a finish record with the achieved truth, a fault firing). The oracle counts execution starts per
operation to find a doubled execution and to check "no effect" claims; observations never count, because reading the world
twice is not acting on it twice.

An unclassified kind counts as an observation, and ``tests/test_judge.py`` fails when a run records a kind that is not
listed here, so a new twin cannot silently escape the duplicate check.
"""

from __future__ import annotations

EXECUTION_START: frozenset[str] = frozenset({
    "move_started", "grip", "z_move", "xy_move", "objective_changed", "tip_picked", "tip_ejected", "transferred",
    "discarded", "thermal_command", "spin_started", "spin_abort_requested", "lid_opened", "lid_closed", "tared",
    "container_moved",
})

OBSERVATION: frozenset[str] = frozenset({
    "move_finished", "move_aborted", "z_reached", "xy_reached", "objective_ready", "thermal_reached", "spin_reached",
    "spin_finished", "spin_aborted", "image_captured", "plate_read", "weighed", "spilled", "air_aspirated", "joint_turned",
    "fault_injected", "fault_fired", "fault_cleared", "object_dropped", "knob_slipped", "joint_stalled",
    "joint_released", "tip_liquid_discarded",
})


def is_start(kind: str) -> bool:
    """Whether an effect of this kind marks an execution start."""
    return kind in EXECUTION_START


def is_known(kind: str) -> bool:
    return kind in EXECUTION_START or kind in OBSERVATION
