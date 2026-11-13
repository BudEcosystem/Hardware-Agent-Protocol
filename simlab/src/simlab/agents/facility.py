"""UC11 truth: Home Assistant is the ground truth of the lights, read by the harness through its own WebSocket session.

The facility devices are a real Home Assistant (the AMD machine's demo container) behind the SimLab adapter. Their state is not
in the world's effect log, so the oracle's usual rules do not apply; the harness keeps an independent poller of the entity states
(``FacilityTruth``) and judges the facility operations with *caller rules* over that record. Those verdicts carry
``truth_source="caller_rule"`` and are never tallied as world-backed.

``prepare_facility`` switches the lights on, starts the poller and, for the manual-press variant, starts a human who flips the
bench light back on a moment after an agent switched it off. ``facility_truth`` stops both and installs the caller rules.

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from simlab.adapters.home_assistant import HomeAssistantLink
from simlab.agents.session import Session
from simlab.agents.tasks import Task
from simlab.runs.judge import Rule

LIGHTS = ("light.bed_light", "light.kitchen_lights")
POLL_S = 0.1
HUMAN_DELAY_S = 0.05


@dataclass
class FacilityTruth:
    link: HomeAssistantLink
    samples: list[tuple[datetime, dict[str, str]]] = field(default_factory=list)
    presses: list[tuple[datetime, str]] = field(default_factory=list)
    tasks: list[asyncio.Task[None]] = field(default_factory=list)

    async def snapshot(self) -> dict[str, str]:
        states = await self.link.states()
        state = {entity: states[entity]["state"] for entity in LIGHTS if entity in states}
        self.samples.append((datetime.now(timezone.utc), state))
        return state

    def state_at(self, when: datetime, entity: str) -> str | None:
        """The first recorded state of ``entity`` at or after ``when`` (the poller samples every 150 ms)."""
        for stamp, state in self.samples:
            if stamp >= when:
                return state.get(entity)
        return self.samples[-1][1].get(entity) if self.samples else None


async def _poll(truth: FacilityTruth) -> None:
    while True:
        await truth.snapshot()
        await asyncio.sleep(POLL_S)


async def _human(truth: FacilityTruth) -> None:
    """A person presses the bench light's switch (turns it back on) shortly after an agent switched it off."""
    while True:
        await asyncio.sleep(POLL_S)
        if truth.samples and truth.samples[-1][1].get("light.bed_light") == "off":
            await asyncio.sleep(HUMAN_DELAY_S)
            await truth.link.request({"type": "call_service", "domain": "light", "service": "turn_on",
                                      "target": {"entity_id": "light.bed_light"}})
            truth.presses.append((datetime.now(timezone.utc), "light.bed_light"))
            return


async def prepare_facility(session: Session, task: Task, ha: tuple[str, str]) -> None:
    link = HomeAssistantLink(ha[0], ha[1])
    truth = FacilityTruth(link)
    for entity in LIGHTS:
        await link.request({"type": "call_service", "domain": "light", "service": "turn_on", "target": {"entity_id": entity}})
    await asyncio.sleep(0.5)
    await truth.snapshot()
    truth.tasks.append(asyncio.create_task(_poll(truth)))
    if task.params.get("manual_press"):
        truth.tasks.append(asyncio.create_task(_human(truth)))
    session.facility = truth  # type: ignore[attr-defined]


async def facility_truth(session: Session) -> None:
    """Stop the poller and the human, take the final state, and install the caller rules for the facility actions."""
    truth: FacilityTruth = session.facility  # type: ignore[attr-defined]
    for task in truth.tasks:
        task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await asyncio.gather(*truth.tasks, return_exceptions=True)
    await truth.snapshot()

    def rule(expected: str) -> Rule:
        def achieved(effects: Any, op: Any) -> bool:
            when = datetime.fromisoformat(str(op.updated_at).replace("Z", "+00:00"))
            entity = op.arguments["entity"]
            overridden = any(stamp >= when and who == entity for stamp, who in truth.presses)  # a person's press wins later
            return truth.state_at(when, entity) in (expected, None) or overridden
        return Rule(achieved)

    session.caller_rules[("facility-1", "turn_on")] = rule("on")
    session.caller_rules[("facility-1", "turn_off")] = rule("off")
    await truth.link.close()
