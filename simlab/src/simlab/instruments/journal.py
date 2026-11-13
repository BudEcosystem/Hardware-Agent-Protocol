"""A protocol instrument's command journal, correlated to adapter operations by an explicit per-command token.

A Modbus, OPC UA or SCPI command cannot carry the BHMS operation id, so the effects an instrument records have no cause. The
adapter therefore numbers every command it sends with a **token** (unique per link) and delivers it in-band as a small
"tag" command sent immediately before the command it labels (Modbus: a write of the token to a tag register; SCPI:
``SYSTem:TAG <n>``; OPC UA: a ``Tag(n)`` method call). The instrument journals the tag **on receipt, before any power or
fault check**, and the next mutating command it receives takes that token. The adapter records, per operation, the tokens it
sent (``CommandLog.sent``). The harness joins the two by token (``attribute``): operation -> tokens -> journal entries ->
effects.

Because the join is by identity, a command the instrument never received (lost on the wire, refused before its callback, cut
by a power loss) is explicit: its token is absent from the journal, or present with ``command_received=False``, and it
attributes nothing, and every later operation still attributes correctly. What cannot be proven is an error:
``AttributionError`` is raised for a token journalled twice, for two operations that sent the same token, and for an entry that
caused effects but carries no token or a token the adapter never sent (an unattributable actor on the instrument).

Neither side reads the other's state; only the tokens tie them.

Thread-safety: runs on the world's event loop.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field

from simlab.world import World


class AttributionError(RuntimeError):
    """The correlation between adapter-sent commands and instrument-journalled commands cannot be proven."""


@dataclass
class JournalEntry:
    number: int
    time_s: float
    token: int | None
    command: str | None = None  # the mutating command taken by this token (None: tag received, command never was)
    command_received: bool = False
    effect_seqs: list[int] = field(default_factory=list)


class CommandJournal:
    """Numbered record of the tags and commands an instrument received and the effects each command caused."""

    def __init__(self, world: World) -> None:
        self.world = world
        self.entries: list[JournalEntry] = []
        self._pending: JournalEntry | None = None

    def tag(self, token: int) -> JournalEntry:
        """A tag arrived (call this first thing on receipt, before any power or fault check)."""
        entry = JournalEntry(len(self.entries), self.world.time_s, token)
        self.entries.append(entry)
        self._pending = entry
        return entry

    @contextmanager
    def command(self, text: str) -> Iterator[JournalEntry]:
        """A mutating command arrived: it takes the pending token (or none if untagged); effects recorded inside the block
        belong to it, even when it fails midway."""
        entry, self._pending = self._pending, None
        if entry is None:
            entry = JournalEntry(len(self.entries), self.world.time_s, None)
            self.entries.append(entry)
        entry.command, entry.command_received = text, True
        first = self.world.effect_count()
        try:
            yield entry
        finally:
            entry.effect_seqs = list(range(first, self.world.effect_count()))


def attribute(journal: CommandJournal, sent: Mapping[str, list[int]]) -> dict[int, str]:
    """Effect sequence number -> operation id for one instrument, joined by token; raises ``AttributionError`` when the join
    cannot be proven (see the module docstring)."""
    owner: dict[int, str] = {}
    for operation_id, tokens in sent.items():
        for token in tokens:
            if token in owner:
                raise AttributionError(f"token {token} was sent by both {owner[token]} and {operation_id}")
            owner[token] = operation_id
    seen: set[int] = set()
    result: dict[int, str] = {}
    for entry in journal.entries:
        if entry.token is None:
            if entry.effect_seqs:
                raise AttributionError(f"instrument command {entry.command!r} (journal entry {entry.number}) caused effects "
                                       "but carried no token: no adapter operation can be blamed")
            continue
        if entry.token in seen:
            raise AttributionError(f"token {entry.token} was journalled twice")
        seen.add(entry.token)
        if entry.token not in owner:
            if entry.effect_seqs:
                raise AttributionError(f"token {entry.token} caused effects but no adapter operation sent it")
            continue
        for seq in entry.effect_seqs:
            result[seq] = owner[entry.token]
    return result
