"""Judging BHMS operation records against ground truth.

For every operation a run made, the oracle needs the claim the runtime recorded (state and effect, from the ``Operation``) and
what would make that claim true in the world. The second is the *rule* for that (device, action): a predicate over the
effects the operation caused (``Oracle.effects_for``, including effects attributed from a protocol instrument's journal) and
the operation's own arguments and result.

Rules compare against **achieved truth**, never against what was commanded: the twins record, when a motion or a heating
ends, where the axis really is (``z_reached``, ``xy_reached``, ``thermal_reached``, ``spin_reached``, ``move_finished``), and
the rules compare those with the commanded target; returned measurements (absorbance, mass, temperature, positions,
volumes) are compared with the world's noiseless value inside the sensor's declared noise. Every action a SimLab device
declares has a rule: an operation with no rule raises ``MissingRule`` (a missing rule is an error, never "consistent").
Adapters whose far end is not in the world (MCP, Home Assistant, Micro-Manager) pass their own rules to ``judge_operations``.

Besides the rules, the oracle checks every record for a doubled execution (``Oracle.duplicates``: execution starts per
cause) and, here, for a second execution under one operation key: operations that share ``(principal, operationKey)`` but
have different operation ids and each executed.

Thread-safety: read-only over a lab; call from its thread.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from simlab.oracle import Verdict, claim_from_operation
from simlab.world import Effect

Rule = Callable[[list[Effect], Any], bool]


class MissingRule(LookupError):
    """No judging rule for a (device, action): the run cannot be judged, which is an error, not a pass."""


def _last(effects: list[Effect], kind: str) -> Effect | None:
    return next((e for e in reversed(effects) if e.kind == kind), None)


def _close(value: Any, truth: float, tolerance: float) -> bool:
    """A returned number matches the world's value (``None``: the device said it could not measure, nothing to compare)."""
    return value is None or abs(float(value) - truth) <= tolerance


def _args(op: Any) -> dict[str, Any]:
    """The arguments as admitted (defaults applied), falling back to those sent."""
    return dict(getattr(op, "admitted_arguments", None) or op.arguments)


# ------------------------------------------------------------------------------------------------ arm


def _moved(effects: list[Effect], op: Any) -> bool:
    done = _last(effects, "move_finished")
    return (done is not None and bool(done.detail["reached"]) and done.detail["site"] == op.arguments["site"]
            and _close(op.result["error_mm"], done.detail["error_mm"], 0.5))


def _grip_closed(effects: list[Effect], op: Any) -> bool:
    grip = _last(effects, "grip")
    holding = op.result["holding"]
    return (grip is not None and grip.detail["close"] is True
            and (holding is None or (grip.detail["holding"] is not None) == holding))


def _grip_opened(effects: list[Effect], op: Any) -> bool:
    grip = _last(effects, "grip")
    return grip is not None and grip.detail["close"] is False


# ------------------------------------------------------------------------------------------------ microscope


def _z_moved(effects: list[Effect], op: Any) -> bool:
    reached = _last(effects, "z_reached")
    return (reached is not None and abs(reached.detail["z_um"] - op.arguments["z"]) <= 0.3
            and _close(op.result["z_um"], reached.detail["z_um"], 0.15))


def _stage_moved(effects: list[Effect], op: Any) -> bool:
    reached = _last(effects, "xy_reached")
    if reached is None:
        return False
    x, y = reached.detail["xy_um"]
    return (abs(x - op.arguments["x"]) <= 1.0 and abs(y - op.arguments["y"]) <= 1.0
            and _close(op.result["x_um"], x, 0.6) and _close(op.result["y_um"], y, 0.6))


def _objective_set(effects: list[Effect], op: Any) -> bool:
    ready = _last(effects, "objective_ready")
    return (ready is not None and ready.detail["index"] == op.arguments["index"] and ready.detail["ready"]
            and op.result["magnification"] == ready.detail["magnification"])


def _captured(effects: list[Effect], op: Any) -> bool:
    """The result must date the frame as the world did: a stale frame returned with its true (old) capture time is honest."""
    frame = _last(effects, "image_captured")
    return (frame is not None and frame.detail["frame_id"] == op.result["frame_id"]
            and abs(frame.detail["captured_s"] - op.result["captured_at_s"]) < 1e-5)


# ------------------------------------------------------------------------------------------------ liquid handler


def _tip_picked(effects: list[Effect], op: Any) -> bool:
    return _last(effects, "tip_picked") is not None


def _tip_ejected(effects: list[Effect], op: Any) -> bool:
    return _last(effects, "tip_ejected") is not None


def _aspirated(effects: list[Effect], op: Any) -> bool:
    transfer = _last(effects, "transferred")
    return (transfer is not None and not _last(effects, "air_aspirated") and not _last(effects, "spilled")
            and abs(transfer.detail["moved_ul"] - op.arguments["volume"]) < 1e-9
            and _close(op.result["aspirated"], transfer.detail["moved_ul"], 1.0))


def _dispensed(effects: list[Effect], op: Any) -> bool:
    transfer = _last(effects, "transferred")
    return (transfer is not None and not _last(effects, "air_aspirated") and not _last(effects, "spilled")
            and abs(transfer.detail["moved_ul"] - op.arguments["volume"]) < 1e-9
            and _close(op.result["dispensed"], transfer.detail["moved_ul"], 1.0))


# ------------------------------------------------------------------------------------------------ reader, balance


def _read_taken(effects: list[Effect], op: Any) -> bool:
    read = _last(effects, "plate_read")
    if read is None or read.detail["wells"] != op.result["wells"]:
        return False
    tolerance = 5 * read.detail["sigma"] + 1e-3
    return all(abs(got - truth) <= tolerance
               for got, truth in zip(op.result["absorbance"], read.detail["true_absorbance"], strict=True))


def _tared(effects: list[Effect], op: Any) -> bool:
    return _last(effects, "tared") is not None


def _weighed(effects: list[Effect], op: Any) -> bool:
    weighed = _last(effects, "weighed")
    return weighed is not None and _close(op.result["mass_g"], weighed.detail["net_g"], 0.01)


# ------------------------------------------------------------------------------------------------ thermal, centrifuge


def _temperature_reached(effects: list[Effect], op: Any) -> bool:
    command, reached = _last(effects, "thermal_command"), _last(effects, "thermal_reached")
    tolerance = float(_args(op).get("tolerance", 0.5))
    return (command is not None and reached is not None and command.detail["setpoint_c"] == op.arguments["target"]
            and abs(reached.detail["temperature_c"] - op.arguments["target"]) <= tolerance
            and _close(op.result["temperature"], reached.detail["temperature_c"], 0.15))


def _heater_off(effects: list[Effect], op: Any) -> bool:
    command = _last(effects, "thermal_command")
    return command is not None and command.detail["enabled"] is False


def _setpoint_written(effects: list[Effect], op: Any) -> bool:
    command = _last(effects, "thermal_command")
    return command is not None and abs(command.detail["setpoint_c"] - op.arguments["value"]) <= 0.05


def _enable_written(effects: list[Effect], op: Any) -> bool:
    command = _last(effects, "thermal_command")
    return command is not None and command.detail["enabled"] is bool(op.arguments["value"])


def _lid_opened(effects: list[Effect], op: Any) -> bool:
    return _last(effects, "lid_opened") is not None


def _lid_closed(effects: list[Effect], op: Any) -> bool:
    return _last(effects, "lid_closed") is not None


def _spun(effects: list[Effect], op: Any) -> bool:
    started, reached = _last(effects, "spin_started"), _last(effects, "spin_reached")
    return (started is not None and reached is not None
            and abs(started.detail["speed_hz"] - op.arguments["speed"]) < 1e-9
            and abs(reached.detail["speed_hz"] - op.arguments["speed"]) <= 0.6
            and _close(op.result["peak_speed"], reached.detail["speed_hz"], 0.5))


def _program_started(effects: list[Effect], op: Any) -> bool:
    started = _last(effects, "spin_started")
    return started is not None and abs(started.detail["speed_hz"] - op.arguments["speed_hz"]) < 1e-9


def _abort_requested(effects: list[Effect], op: Any) -> bool:
    return _last(effects, "spin_abort_requested") is not None


RULES: dict[tuple[str, str], Rule] = {
    ("arm-1", "move_to_site"): _moved,
    ("arm-1", "close_gripper"): _grip_closed,
    ("arm-1", "open_gripper"): _grip_opened,
    ("microscope-1", "set_z"): _z_moved,
    ("microscope-1", "move_stage"): _stage_moved,
    ("microscope-1", "set_objective"): _objective_set,
    ("microscope-1", "snap"): _captured,
    ("lh-1", "pick_up_tip"): _tip_picked,
    ("lh-1", "eject_tip"): _tip_ejected,
    ("lh-1", "aspirate"): _aspirated,
    ("lh-1", "dispense"): _dispensed,
    ("reader-1", "read_absorbance"): _read_taken,
    ("balance-1", "tare"): _tared,
    ("balance-1", "weigh"): _weighed,
    ("thermal-1", "set_temperature"): _temperature_reached,
    ("thermal-1", "disable"): _heater_off,
    ("centrifuge-1", "open_lid"): _lid_opened,
    ("centrifuge-1", "close_lid"): _lid_closed,
    ("centrifuge-1", "spin"): _spun,
    # protocol-bridged instruments: their effects are attributed from the instrument journals (Lab.attribute_bridged)
    ("thermal-m1", "set_setpoint"): _setpoint_written,
    ("thermal-m1", "set_enabled"): _enable_written,
    ("centrifuge-u1", "start_program"): _program_started,
    ("centrifuge-u1", "open_lid"): _lid_opened,
    ("centrifuge-u1", "close_lid"): _lid_closed,
    ("centrifuge-u1", "abort"): _abort_requested,
    ("balance-s1", "tare"): _tared,
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
    """The oracle's verdict on every operation record (see the module docstring); raises ``MissingRule`` for an action
    nobody wrote a rule for."""
    table = {**RULES, **(rules or {})}
    executed_under_key: dict[tuple[Any, Any], set[str]] = defaultdict(set)
    for op in operations:
        if oracle.start_effects(op.operation_id):
            executed_under_key[(getattr(op, "principal", None), op.operation_key)].add(op.operation_id)
    judged = []
    for op in operations:
        try:
            rule = table[(op.device_id, op.action)]
        except KeyError:
            raise MissingRule(f"no judging rule for {op.device_id}/{op.action}") from None
        effects = oracle.effects_for(op.operation_id)

        def expect(_snapshot: dict[str, Any], rule: Rule = rule, effects: list[Effect] = effects, op: Any = op) -> bool:
            return True if op.state != "completed" else bool(rule(effects, op))

        verdict = oracle.judge(claim_from_operation(op, expect))
        if len(executed_under_key[(getattr(op, "principal", None), op.operation_key)]) > 1:
            verdict = Verdict.DUPLICATE_EFFECT  # two executions under one operation key
        judged.append(Judged(op.device_id, op.action, dict(op.arguments), op.operation_id, op.state, op.effect, verdict))
    return judged
