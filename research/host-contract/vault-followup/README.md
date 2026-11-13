# SQLite file identity and recovery constraints

The official [SQLite corruption reference](https://sqlite.org/howtocorrupt.html)
is retained as [raw HTML](raw/corruption.html), [extracted text](text/corruption.txt)
and hashed metadata. All **765 LF lines** were read. The only inventoried image
is the decorative banner; no acquired code or linked controller was executed.
[Reading receipt](reading.json).

The source explains that ordinary file access can bypass SQLite coordination:
closing a separate descriptor in the same process can cancel POSIX database locks.
It also covers mismatched or removed journals, live-file backup, pathname/link
ambiguity, inherited connections across fork, inconsistent lock protocols and
storage that fails to honor synchronization. SQLite cannot protect ordinary files
from arbitrary external overwrites. Newer defensive behavior is version-specific;
the local 3.45.1 build cannot be assumed to include later fixes. The page also
records historical configuration/implementation failures, including WAL-specific
conditions; those conditions must not be generalized to every journaling profile.

The [vault candidate](../../../artifacts/implementation/pat-evidence-vault/README.md)
therefore holds its identity descriptor until after SQLite closes, verifies private
ownership and exact paths, rejects additional links, and refuses retained sidefiles
without deleting them. These are original design choices under a cooperative
owner model. Its read-only audit uses quiescent state and verifies hashes before
and after. The passing fixtures do not establish filesystem or power-loss
qualification. Linked bug reports, platform references and wider recovery testing
remain separate research/implementation work.
