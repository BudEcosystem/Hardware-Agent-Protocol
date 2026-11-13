"""A protocol instrument's command journal: which world effects each command it received produced.

A Modbus, OPC UA or SCPI command cannot carry the BHMS operation id, so the effects an instrument records have no cause.
Each instrument therefore keeps a journal: command number ``n`` (counting only commands that can change something, in the
order received) and the sequence numbers of the effects recorded while it ran. The adapter, on its side, counts the commands
it sends and records, per operation, the range of command numbers it sent (``CommandLog.sent``). The harness joins the two
(``Lab.attribute_bridged``): operation -> command numbers -> effects, and tells the oracle (``Oracle.attribute``). Neither
side reads the other's state; only the ordering of one connection ties them.

Thread-safety: runs on the world's event loop.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from simlab.world import World


@dataclass
class JournalEntry:
    number: int
    time_s: float
    command: str
    effect_seqs: list[int] = field(default_factory=list)


class CommandJournal:
    """Numbered record of the commands an instrument received and the effects each caused."""

    def __init__(self, world: World) -> None:
        self.world = world
        self.entries: list[JournalEntry] = []

    @contextmanager
    def command(self, text: str) -> Iterator[JournalEntry]:
        """Record one received command; effects recorded inside the block belong to it (even when it fails midway)."""
        entry = JournalEntry(len(self.entries), self.world.time_s, text)
        self.entries.append(entry)
        first = self.world.effect_count()
        try:
            yield entry
        finally:
            entry.effect_seqs = list(range(first, self.world.effect_count()))
