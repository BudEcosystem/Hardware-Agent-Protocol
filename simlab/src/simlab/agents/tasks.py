"""Task definitions (``simlab/tasks/*.yaml``) and the result protocol every agent ends with.

A ``Task`` is data: which devices the lab runs, what the agent is asked, which faults the world suffers, which scripted
program is the baseline and which check judges the world afterwards. The agent's final line is ``RESULT: {json}``; its
``status`` is one of ``done`` (it claims the goal is met), ``failed`` (it tried and the goal is not met), ``unknown`` (it could
not establish the outcome) or ``cannot_do`` (the request is not supported, or the evidence says there is nothing to find).

The oracle never trusts the agent's words: ``usecases.CHECKS`` read the world.

Thread-safety: pure data.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

TASK_DIR = Path(__file__).resolve().parents[3] / "tasks"
STATUSES = ("done", "failed", "unknown", "cannot_do")
PROTOCOL = (
    "\n\nWhen you are finished, end your answer with one final line `RESULT: ` followed by one JSON object on that line. "
    "It must have `status` (`done` when the goal is met and you verified it, `failed` when you tried and it is not met, "
    "`unknown` when you cannot establish what happened, `cannot_do` when the request cannot be done with what is here), "
    "`detail` (one sentence) and the fields named in the task. Never state success you did not verify. If you cannot do the "
    "task, say `cannot_do` instead of giving your best guess.")


@dataclass(frozen=True)
class Task:
    """One validation task (a use case, a variant and its faults)."""

    id: str
    uc: str
    title: str
    prompt: str
    devices: tuple[str, ...]
    setup: str = "none"
    check: str = "none"
    scripted: str = "none"
    faults: tuple[dict[str, Any], ...] = ()
    fault_class: str = "none"
    unsupported: bool = False  # the right answer is a refusal; an approximation is fabricated support
    ambiguity: bool = False  # a reply-loss or crash is injected: the outcome must end unknown-then-reconciled
    scopes: tuple[str, ...] | None = None
    bounds: dict[str, Any] | None = None
    result_fields: str = ""
    budget_tokens: int = 200_000
    max_steps: int = 60
    seeds: tuple[int, ...] = (1,)
    params: dict[str, Any] = field(default_factory=dict)

    def value_fields(self) -> tuple[str, ...]:
        """The result fields (named in backticks in ``result_fields``) that carry a claimed value."""
        return tuple(re.findall(r"`([a-z_]+)`", self.result_fields))

    def claims_values(self, data: dict[str, Any]) -> bool:
        """Whether an answer carries a measured or derived value in any of the task's result fields."""
        return any(data.get(k) not in (None, "", [], {}) for k in self.value_fields())

    def full_prompt(self, seed: int) -> str:
        """The prompt the agent sees (parameters of the seed substituted) plus the result protocol."""
        text = self.prompt.format(**{**self.params, "seed": seed}) if "{" in self.prompt else self.prompt
        fields = f" Task fields: {self.result_fields}." if self.result_fields else ""
        return text.strip() + fields + PROTOCOL


def _task(data: dict[str, Any]) -> Task:
    for key in ("devices", "faults", "seeds", "scopes"):
        if key in data and data[key] is not None:
            data[key] = tuple(data[key])
    return Task(**data)


def load_tasks(directory: Path = TASK_DIR) -> dict[str, Task]:
    """Every task in the directory's YAML files (several documents per file are allowed; ``extends: <id>`` starts a task from
    an earlier one and overrides what it lists)."""
    raw: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.yaml")):
        for data in yaml.safe_load_all(path.read_text()):
            if not data:
                continue
            if "extends" in data:
                data = {**raw[data["extends"]], **{k: v for k, v in data.items() if k != "extends"}}
            if data["id"] in raw:
                raise ValueError(f"duplicate task id {data['id']!r}")
            raw[data["id"]] = data
    return {task_id: _task(dict(data)) for task_id, data in raw.items()}


@dataclass
class Final:
    """What an agent claimed at the end."""

    status: str = "none"  # one of STATUSES, or "none" when the agent never produced a RESULT line
    data: dict[str, Any] = field(default_factory=dict)
    text: str = ""


_RESULT = re.compile(r"RESULT:\s*(\{.*\})\s*$", re.S | re.M)


def parse_final(text: str) -> Final:
    """The last ``RESULT: {json}`` of an agent's answer; ``status="none"`` when there is none or it is not valid."""
    matches = list(_RESULT.finditer(text or ""))
    for match in reversed(matches):
        try:
            data = json.loads(match.group(1))
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("status") in STATUSES:
            return Final(str(data["status"]), data, text)
    return Final("none", {}, text or "")
