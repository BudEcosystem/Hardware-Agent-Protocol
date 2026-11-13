"""Shared builders for the SimLab tests (real worlds and twins; nothing is mocked)."""

from __future__ import annotations

from simlab.faults import Fault, OnEvent
from simlab.scene import BENCH
from simlab.twins.arm import ArmTwin
from simlab.twins.microscope import MicroscopeTwin
from simlab.world import SceneParams, World


def lab(seed: int = 1, **params):
    """A world with the arm twin: ``(world, arm)``."""
    world = World(BENCH, seed=seed, params=SceneParams(**params) if params else None)
    return world, ArmTwin(world)


def scope_lab(seed: int = 1, *, with_slide_on_stage: bool = True, specimen_z_um: float = 40.0, **params):
    """A world with a microscope twin (and a slide on the stage unless told otherwise): ``(world, scope)``."""
    world = World(BENCH, seed=seed, params=SceneParams(**params) if params else None, attach_arm=False)
    world.ledger.add_container("slide", "slide", {}, "microscope_stage" if with_slide_on_stage else "slide_rack",
                               meta={"specimen_z_um": specimen_z_um})
    return world, MicroscopeTwin(world)


def bench(seed: int = 1, *, specimen_z_um: float = 40.0, slide_site: str = "slide_rack", **params):
    """A world with the arm and the microscope twin sharing it: ``(world, arm, scope)``."""
    world = World(BENCH, seed=seed, params=SceneParams(**params) if params else None)
    world.ledger.add_container("slide", "slide", {}, slide_site, meta={"specimen_z_um": specimen_z_um})
    return world, ArmTwin(world), MicroscopeTwin(world)


def inject_drop_during_next_carry(world: World, delay_s: float = 0.3) -> str:
    """Arm a drop of the plate that fires ``delay_s`` into the next move made while the plate is in the gripper."""
    return world.faults.inject(Fault("plate", "drop_object", OnEvent("move_started"),
                                     {"require_location": "in_gripper", "delay_s": delay_s}))


def carry_plate(arm: ArmTwin, to: str, cause: str, source: str = "hotel") -> None:
    """Pick the plate at ``source``, carry it to ``to`` and open the jaw there (what the plan's tests call a carry)."""
    arm.move_to_site(source, cause=f"{cause}:pick")  # one execution per cause: the carry's own cause is its last move
    arm.grip(True, cause=f"{cause}:grab")
    arm.move_to_site(to, cause=cause)
    arm.grip(False, cause=cause)


def turn(world: World, joint: str, rad: float) -> None:
    """A human turns a knob."""
    world.turn_joint(joint, rad, cause=None)
