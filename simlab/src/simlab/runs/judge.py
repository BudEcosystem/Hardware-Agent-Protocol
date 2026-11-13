"""Judging BHMS operation records against ground truth.

For every operation a run made, the oracle needs the claim the runtime recorded (state and effect, from the ``Operation``) and
what would make that claim true in the world. That is the *rule* for the (device, action): two predicates over the effects the
operation caused (``Oracle.effects_for``, including effects attributed from a protocol instrument's journal) and the
operation's own arguments and result:

* ``achieved``: did the world end up where the record says (commanded target against the achieved truth the twins record when
  a motion, heating or spin ends);
* ``values``: are the returned numbers true within the sensor's declared noise, or ``null``? A false value fails the claim
  whatever its effect certainty (``Claim.values``): a hedge covers what a record does not know, not what it makes up.

Every action a SimLab device declares has a rule; an operation with no rule raises ``MissingRule``. Adapters whose far end
is not in the world (MCP, Home Assistant, Micro-Manager) pass their own rules; a caller rule may not replace a world rule
(``ValueError``), and its verdicts carry ``truth_source="caller_rule"`` so a tally can never count them as world-backed.

Beyond the rules, the oracle checks every record for a doubled execution (``Oracle.duplicates``: execution starts per cause)
and this module checks for a second execution under one operation key. An ``Operation`` record carries no principal, so
grouping is by ``(principal_of(op), operationKey)`` with ``principal_of`` defaulting to "the record's ``principal`` attribute
if it has one": **the default assumes a single principal** (one agent per run, as in every SimLab run). A harness with several
principals passes ``principal_of``.

A non-completed record that claims ``verified`` is judged against the same ``achieved`` predicate (evaluated defensively,
because a failed record has no result): a verified claim the world does not back is false.

Thread-safety: read-only over a lab; call from its thread.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from simlab.oracle import Verdict, claim_from_operation
from simlab.world import Effect

Check = Callable[[list[Effect], Any], bool]


@dataclass(frozen=True)
class Rule:
    """What makes a record's claim true: ``achieved`` (the world) and ``values`` (the returned numbers), over the operation's
    effects and its record."""

    achieved: Check
    values: Check | None = None


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


def _values_of(kind: str, compare: Callable[[Effect, Any], bool]) -> Check:
    """A values check against the truth effect of ``kind``; a returned value with no truth to compare it to is false."""
    def check(effects: list[Effect], op: Any) -> bool:
        truth = _last(effects, kind)
        return truth is not None and compare(truth, op)
    return check


# ------------------------------------------------------------------------------------------------ arm


def _moved(effects: list[Effect], op: Any) -> bool:
    done = _last(effects, "move_finished")
    return done is not None and bool(done.detail["reached"]) and done.detail["site"] == op.arguments["site"]


def _grip_closed(effects: list[Effect], op: Any) -> bool:
    grip = _last(effects, "grip")
    return grip is not None and grip.detail["close"] is True


def _grip_opened(effects: list[Effect], op: Any) -> bool:
    grip = _last(effects, "grip")
    return grip is not None and grip.detail["close"] is False


# ------------------------------------------------------------------------------------------------ microscope


def _z_moved(effects: list[Effect], op: Any) -> bool:
    reached = _last(effects, "z_reached")
    return reached is not None and abs(reached.detail["z_um"] - op.arguments["z"]) <= 0.3


def _stage_moved(effects: list[Effect], op: Any) -> bool:
    reached = _last(effects, "xy_reached")
    if reached is None:
        return False
    x, y = reached.detail["xy_um"]
    return abs(x - op.arguments["x"]) <= 1.0 and abs(y - op.arguments["y"]) <= 1.0


def _objective_set(effects: list[Effect], op: Any) -> bool:
    ready = _last(effects, "objective_ready")
    return ready is not None and ready.detail["index"] == op.arguments["index"] and bool(ready.detail["ready"])


def _captured(effects: list[Effect], op: Any) -> bool:
    return _last(effects, "image_captured") is not None


# ------------------------------------------------------------------------------------------------ liquid handler


def _tip_picked(effects: list[Effect], op: Any) -> bool:
    return _last(effects, "tip_picked") is not None


def _tip_ejected(effects: list[Effect], op: Any) -> bool:
    return _last(effects, "tip_ejected") is not None


def _moved_exactly(effects: list[Effect], op: Any) -> bool:
    transfer = _last(effects, "transferred")
    return (transfer is not None and not _last(effects, "air_aspirated") and not _last(effects, "spilled")
            and abs(transfer.detail["moved_ul"] - op.arguments["volume"]) < 1e-9)


# ------------------------------------------------------------------------------------------------ reader, balance


def _read_taken(effects: list[Effect], op: Any) -> bool:
    return _last(effects, "plate_read") is not None


def _absorbance_true(read: Effect, op: Any) -> bool:
    if read.detail["wells"] != op.result["wells"]:
        return False
    tolerance = 5 * read.detail["sigma"] + 1e-3
    return all(abs(got - truth) <= tolerance
               for got, truth in zip(op.result["absorbance"], read.detail["true_absorbance"], strict=True))


def _tared(effects: list[Effect], op: Any) -> bool:
    return _last(effects, "tared") is not None


def _weighed(effects: list[Effect], op: Any) -> bool:
    return _last(effects, "weighed") is not None


# ------------------------------------------------------------------------------------------------ thermal, centrifuge


def _temperature_reached(effects: list[Effect], op: Any) -> bool:
    command, reached = _last(effects, "thermal_command"), _last(effects, "thermal_reached")
    tolerance = float(_args(op).get("tolerance", 0.5))
    return (command is not None and reached is not None and command.detail["setpoint_c"] == op.arguments["target"]
            and abs(reached.detail["temperature_c"] - op.arguments["target"]) <= tolerance)


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
            and abs(reached.detail["speed_hz"] - op.arguments["speed"]) <= 0.6)


def _program_started(effects: list[Effect], op: Any) -> bool:
    started = _last(effects, "spin_started")
    return started is not None and abs(started.detail["speed_hz"] - op.arguments["speed_hz"]) < 1e-9


def _abort_requested(effects: list[Effect], op: Any) -> bool:
    """The instrument received the abort: it braked a running rotor, or it recorded that there was nothing to brake."""
    return _last(effects, "spin_abort_requested") is not None or _last(effects, "spin_abort_ignored") is not None


def _knob_turned(effects: list[Effect], op: Any) -> bool:
    """The Actuator Node drove the commanded knob through the commanded number of revolutions (what the node did; what the
    axis then did is the microscope's business)."""
    started = _last(effects, "actuator_turn")
    return (started is not None and started.detail["joint"] == op.arguments["knob"]
            and abs(started.detail["revolutions"] - float(op.arguments["revolutions"])) < 1e-9)


RULES: dict[tuple[str, str], Rule] = {
    ("knob-1", "turn"): Rule(_knob_turned),
    ("notice-1", "post"): Rule(lambda effects, op: not effects),
    ("clock-1", "wait"): Rule(lambda effects, op: not effects),
    ("arm-1", "move_to_site"): Rule(_moved, _values_of("move_finished", lambda t, op: _close(op.result["error_mm"],
                                                                                              t.detail["error_mm"], 0.5))),
    ("arm-1", "close_gripper"): Rule(_grip_closed, _values_of(
        "grip", lambda t, op: op.result["holding"] is None or (t.detail["holding"] is not None) == op.result["holding"])),
    ("arm-1", "open_gripper"): Rule(_grip_opened),
    ("microscope-1", "set_z"): Rule(_z_moved, _values_of("z_reached", lambda t, op: _close(op.result["z_um"],
                                                                                           t.detail["z_um"], 0.15))),
    ("microscope-1", "move_stage"): Rule(_stage_moved, _values_of("xy_reached", lambda t, op: (
        _close(op.result["x_um"], t.detail["xy_um"][0], 0.6) and _close(op.result["y_um"], t.detail["xy_um"][1], 0.6)))),
    ("microscope-1", "set_objective"): Rule(_objective_set, _values_of(
        "objective_ready", lambda t, op: op.result["magnification"] == t.detail["magnification"])),
    ("microscope-1", "snap"): Rule(_captured, _values_of("image_captured", lambda t, op: (
        # a stale frame returned with its true (old) capture time is honest
        t.detail["frame_id"] == op.result["frame_id"] and abs(t.detail["captured_s"] - op.result["captured_at_s"]) < 1e-5))),
    ("lh-1", "pick_up_tip"): Rule(_tip_picked),
    ("lh-1", "eject_tip"): Rule(_tip_ejected),
    ("lh-1", "aspirate"): Rule(_moved_exactly, _values_of("transferred", lambda t, op: _close(
        op.result["aspirated"], t.detail["moved_ul"], 1.0))),
    ("lh-1", "dispense"): Rule(_moved_exactly, _values_of("transferred", lambda t, op: _close(
        op.result["dispensed"], t.detail["moved_ul"], 1.0))),
    ("reader-1", "read_absorbance"): Rule(_read_taken, _values_of("plate_read", _absorbance_true)),
    ("balance-1", "tare"): Rule(_tared),
    ("balance-1", "weigh"): Rule(_weighed, _values_of("weighed", lambda t, op: _close(op.result["mass_g"],
                                                                                      t.detail["net_g"], 0.01))),
    ("thermal-1", "set_temperature"): Rule(_temperature_reached, _values_of(
        "thermal_reached", lambda t, op: _close(op.result["temperature"], t.detail["temperature_c"], 0.15))),
    ("thermal-1", "disable"): Rule(_heater_off),
    ("centrifuge-1", "open_lid"): Rule(_lid_opened),
    ("centrifuge-1", "close_lid"): Rule(_lid_closed),
    ("centrifuge-1", "spin"): Rule(_spun, _values_of("spin_reached", lambda t, op: _close(
        op.result["peak_speed"], t.detail["speed_hz"], 0.5))),
    # protocol-bridged instruments: their effects are attributed from the instrument journals (Lab.attribute_bridged)
    ("thermal-m1", "set_setpoint"): Rule(_setpoint_written),
    ("thermal-m1", "set_enabled"): Rule(_enable_written),
    ("centrifuge-u1", "start_program"): Rule(_program_started),
    ("centrifuge-u1", "open_lid"): Rule(_lid_opened),
    ("centrifuge-u1", "close_lid"): Rule(_lid_closed),
    ("centrifuge-u1", "abort"): Rule(_abort_requested),
    ("balance-s1", "tare"): Rule(_tared),
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
    truth_source: str  # "world": a SimLab rule over the world's effect log; "caller_rule": a rule the caller supplied


def _safe(check: Check | None, effects: list[Effect], op: Any) -> bool:
    """Evaluate a check; a record too incomplete for it (a failed record has no result) fails the check."""
    if check is None:
        return True
    try:
        return bool(check(effects, op))
    except (KeyError, TypeError, IndexError, AttributeError):
        return False


def judge_operations(oracle: Any, operations: list[Any],
                     rules: dict[tuple[str, str], Rule | Check] | None = None, *,
                     principal_of: Callable[[Any], Any] | None = None) -> list[Judged]:
    """The oracle's verdict on every operation record (see the module docstring); raises ``MissingRule`` for an action
    nobody wrote a rule for and ``ValueError`` when ``rules`` tries to override a world rule."""
    caller = {key: value if isinstance(value, Rule) else Rule(value) for key, value in (rules or {}).items()}
    clash = sorted(set(caller) & set(RULES))
    if clash:
        raise ValueError(f"caller rules may not replace world rules: {clash}")
    table = {**RULES, **caller}
    principal_of = principal_of or (lambda op: getattr(op, "principal", None))
    executed_under_key: dict[tuple[Any, Any], set[str]] = defaultdict(set)
    for op in operations:
        if oracle.start_effects(op.operation_id):
            executed_under_key[(principal_of(op), op.operation_key)].add(op.operation_id)
    judged = []
    for op in operations:
        try:
            rule = table[(op.device_id, op.action)]
        except KeyError:
            raise MissingRule(f"no judging rule for {op.device_id}/{op.action}") from None
        effects = oracle.effects_for(op.operation_id)

        def expect(_snapshot: dict[str, Any], rule: Rule = rule, effects: list[Effect] = effects, op: Any = op) -> bool:
            if op.state == "completed":
                return _safe(rule.achieved, effects, op)
            if op.effect == "verified":  # a verified claim on a record that did not complete still has to be true
                return _safe(rule.achieved, effects, op)
            return True

        def values(_snapshot: dict[str, Any], rule: Rule = rule, effects: list[Effect] = effects, op: Any = op) -> bool:
            return _safe(rule.values, effects, op)

        verdict = oracle.judge(claim_from_operation(op, expect, values if rule.values is not None else None))
        if len(executed_under_key[(principal_of(op), op.operation_key)]) > 1:
            verdict = Verdict.DUPLICATE_EFFECT  # two executions under one operation key
        judged.append(Judged(op.device_id, op.action, dict(op.arguments), op.operation_id, op.state, op.effect, verdict,
                             "caller_rule" if (op.device_id, op.action) in caller else "world"))
    return judged
