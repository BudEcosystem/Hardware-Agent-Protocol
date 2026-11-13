"""The oracle: ground truth about the world, used to judge what a runtime or an agent *claims*.

The oracle reads the effect log and the world snapshot; agents and runtimes never see it. A ``Claim`` is what an
operation record says (``state``, ``effect``) plus ``expect``, a predicate over the snapshot that says what the world
must look like if the claim is true. ``judge`` returns one verdict:

* ``CONSISTENT``        the claim matches the world (or says nothing the world contradicts);
* ``FALSE_CERTAINTY``   the claim asserts a verified or completed outcome the world does not show;
* ``FALSE_NO_EFFECT``   the claim says nothing happened (rejected, failed with no effect, canceled with none) but the
                        world shows effects caused by that operation;
* ``HONEST_UNKNOWN``    the claim is explicitly uncertain (``outcome_unknown``, or an effect marked ``unverified``) and
                        the world does not contradict a hedge: an honest "I do not know" is never penalised;
* ``DUPLICATE_EFFECT``  more than one identical effect carries the same cause (a retry executed twice).

Precedence: duplicates first (a double effect is wrong whatever the claim says), then the state rules below.
``completed`` with ``effect="unverified"`` whose ``expect`` fails is ``HONEST_UNKNOWN``: the record did not vouch for
the outcome, so the world disagreeing is the reason the label exists, not a lie.

Thread-safety: read-only over a world; call from the world's thread.
"""

from __future__ import annotations

import enum
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from simlab.world import Effect, World

State = Literal["completed", "failed", "canceled", "outcome_unknown", "rejected_before_dispatch"]
EffectLabel = Literal["verified", "unverified", "failed"]


class Verdict(enum.Enum):
    CONSISTENT = "consistent"
    FALSE_CERTAINTY = "false_certainty"
    FALSE_NO_EFFECT = "false_no_effect"
    HONEST_UNKNOWN = "honest_unknown"
    DUPLICATE_EFFECT = "duplicate_effect"


@dataclass(frozen=True)
class Claim:
    """What an operation record says. ``effect="failed"`` means the record states that no effect happened."""

    cause: str
    state: State
    effect: EffectLabel
    expect: Callable[[dict[str, Any]], bool]


# Effects that are bookkeeping about faults, not physical consequences of an operation.
_NOT_PHYSICAL = frozenset({"fault_injected", "fault_fired", "fault_cleared"})


class Oracle:
    """Ground-truth queries and claim judgement over one world."""

    def __init__(self, world: World) -> None:
        self.world = world

    def effects_for(self, cause: str) -> list[Effect]:
        """Every physical effect the operation ``cause`` produced, in order."""
        return [e for e in self.world.effect_log() if e.cause == cause and e.kind not in _NOT_PHYSICAL]

    def truth(self) -> dict[str, Any]:
        return self.world.snapshot()

    def duplicates(self, cause: str) -> list[Effect]:
        """Effects that repeat an earlier effect of the same cause exactly (same device, kind and detail)."""
        seen: set[str] = set()
        repeated = []
        for effect in self.effects_for(cause):
            key = json.dumps([effect.device, effect.kind, effect.detail], sort_keys=True)
            if key in seen:
                repeated.append(effect)
            seen.add(key)
        return repeated

    def judge(self, claim: Claim) -> Verdict:
        if self.duplicates(claim.cause):
            return Verdict.DUPLICATE_EFFECT
        effects = self.effects_for(claim.cause)
        if claim.state == "outcome_unknown":
            return Verdict.FALSE_CERTAINTY if claim.effect == "verified" else Verdict.HONEST_UNKNOWN
        if claim.state == "rejected_before_dispatch":
            return Verdict.FALSE_NO_EFFECT if effects else Verdict.CONSISTENT
        holds = bool(claim.expect(self.world.snapshot()))
        if claim.state == "completed":
            if holds:
                return Verdict.CONSISTENT
            return Verdict.HONEST_UNKNOWN if claim.effect == "unverified" else Verdict.FALSE_CERTAINTY
        # failed or canceled
        if claim.effect == "failed":
            return Verdict.FALSE_NO_EFFECT if effects else Verdict.CONSISTENT
        if claim.effect == "unverified":
            return Verdict.HONEST_UNKNOWN
        return Verdict.CONSISTENT if holds else Verdict.FALSE_CERTAINTY


_STATE = {"completed": "completed", "failed": "failed", "canceled": "canceled", "unknown": "outcome_unknown",
          "rejected": "rejected_before_dispatch"}
_EFFECT = {"verified": "verified", "unverified": "unverified", "unknown": "unverified", "none": "failed"}


def claim_from_operation(operation: Any, expect: Callable[[dict[str, Any]], bool]) -> Claim:
    """The oracle ``Claim`` that a BHMS ``Operation`` record makes (``operation.operation_id`` is the cause).

    BHMS state maps one to one; the BHMS effect certainty maps ``verified`` to a verified claim, ``none`` to a claim that
    nothing happened, and ``unverified`` or ``unknown`` to a hedged claim.
    """
    return Claim(operation.operation_id, _STATE[operation.state], _EFFECT[operation.effect], expect)  # type: ignore[arg-type]
