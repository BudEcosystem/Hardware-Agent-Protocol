"""Judging BHMS operation records against ground truth.

For every operation a run made, the oracle needs two things: the claim the runtime recorded (state and effect, from the
``Operation``) and what would make that claim true in the world. The second is the *rule* for that (device, action): a
predicate over the effects the operation caused (``Oracle.effects_for``) and the operation's own arguments and result. Rules
read the world's effect log, the one account that is time-local (the final world state no longer says what an earlier
operation did).

A rule answers "if this operation really did what it says, what must the world have recorded?". Operations whose effects the
world cannot attribute (a protocol instrument cannot know the BHMS operation id that caused a register write) are judged by
the model state the instrument serves.

Thread-safety: read-only over a lab; call from its thread.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from simlab.oracle import Verdict, claim_from_operation
from simlab.world import Effect

Rule = Callable[[list[Effect], Any], bool]


def _effect(effects: list[Effect], kind: str) -> Effect | None:
    return next((e for e in reversed(effects) if e.kind == kind), None)


def _moved(effects: list[Effect], op: Any) -> bool:
    done = _effect(effects, "move_finished")
    return done is not None and bool(done.detail["reached"]) and done.detail["site"] == op.arguments["site"]


def _grip_closed(effects: list[Effect], op: Any) -> bool:
    grip = _effect(effects, "grip")
    return grip is not None and grip.detail["close"] is True and (grip.detail["holding"] is not None) == op.result["holding"]


def _grip_opened(effects: list[Effect], op: Any) -> bool:
    grip = _effect(effects, "grip")
    return grip is not None and grip.detail["close"] is False


def _z_moved(effects: list[Effect], op: Any) -> bool:
    move = _effect(effects, "z_move")
    return move is not None and abs(move.detail["to_um"] - op.arguments["z"]) < 1e-9


def _stage_moved(effects: list[Effect], op: Any) -> bool:
    move = _effect(effects, "xy_move")
    return move is not None and move.detail["to_um"] == [op.arguments["x"], op.arguments["y"]]


def _captured(effects: list[Effect], op: Any) -> bool:
    frame = _effect(effects, "image_captured")
    return frame is not None and not frame.detail["stale"] and frame.detail["frame_id"] == op.result["frame_id"]


def _liquid_moved(effects: list[Effect], op: Any) -> bool:
    transfer = _effect(effects, "transferred")
    return (transfer is not None and not _effect(effects, "air_aspirated") and not _effect(effects, "spilled")
            and transfer.detail["moved_ul"] == op.arguments["volume"])


def _read_taken(effects: list[Effect], op: Any) -> bool:
    return _effect(effects, "plate_read") is not None


RULES: dict[tuple[str, str], Rule] = {
    ("arm-1", "move_to_site"): _moved,
    ("arm-1", "close_gripper"): _grip_closed,
    ("arm-1", "open_gripper"): _grip_opened,
    ("microscope-1", "set_z"): _z_moved,
    ("microscope-1", "move_stage"): _stage_moved,
    ("microscope-1", "snap"): _captured,
    ("lh-1", "aspirate"): _liquid_moved,
    ("lh-1", "dispense"): _liquid_moved,
    ("reader-1", "read_absorbance"): _read_taken,
}


@dataclass(frozen=True)
class Judged:
    device: str
    action: str
    arguments: dict[str, Any]
    operation_id: str
    state: str
    effect: str
    verdict: Verdict


def judge_operations(oracle: Any, operations: list[Any], rules: dict[tuple[str, str], Rule] | None = None) -> list[Judged]:
    """The oracle's verdict on every operation record (see the module docstring)."""
    table = {**RULES, **(rules or {})}
    judged = []
    for op in operations:
        rule = table.get((op.device_id, op.action))
        effects = oracle.effects_for(op.operation_id)

        def expect(_snapshot: dict[str, Any], rule: Rule | None = rule, effects: list[Effect] = effects,
                   op: Any = op) -> bool:
            return (bool(effects) or op.effect == "none") if rule is None else rule(effects, op)

        judged.append(Judged(op.device_id, op.action, dict(op.arguments), op.operation_id, op.state, op.effect,
                             oracle.judge(claim_from_operation(op, expect))))
    return judged
