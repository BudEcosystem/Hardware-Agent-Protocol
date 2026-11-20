# SQLite capacity experiments and retained-state observation

This original host-only work executes no hardware, HMS runtime, worker, acquired
code, or network operation. It does not change an existing database. All old
passing and failed scopes remain intact. It is not a production storage provider.

`source01/probe.py` attempts five cases in one fresh
`attempts/attempt01/scratch` directory; it stops at the ATTACH authorizer.
The source-02 correction uses `attempts/attempt02/scratch` and the same limits.
The complete passing probe uses six SQLite connections and one
explicitly named attachment. Loops, row sizes and page limits are constants.
Each database has at most 64 1,024-byte pages. DELETE journals and synchronous
EXTRA remain enabled. Only rows created by the freelist experiment are deleted;
no goal history or failed run is cleaned up. SQLITE_FULL is an expected test
condition, with explicit transaction-state observation and rollback if active.

The original parent allows one child, 30 seconds, 64 KiB per output stream,
1 MiB per file, 32 scratch files and 8 MiB retained scratch. Child limits are
15 CPU seconds, 256 MiB address space and 1 MiB per file. These are below the
existing runtime test limits. Filesystem aggregate quota is not enforced by
this harness; fixed SQL and finite loops constrain this trusted experiment.
Any failure is retained without automatic retry or increased limits.

`source01/audit-allocation.py` reacquires existing owner/writer locks and reads
only the original and retained copy of the previous passing authority database.
Both hashes must match its sealed index before and after observation. Hot journal,
WAL or shared-memory sidefiles cause refusal. Two immutable read-only connections
query at most 256 DBSTAT object rows, with query progress/time bounds. No extension
is loaded or virtual table created. Missing DBSTAT support is a failure, not a
reason to modify the retained database. Read access can affect OS access-time
metadata; content hashes and file sizes, rather than all filesystem metadata,
are the unchanged-state claim.

The primary agent reviews and freezes these sources before execution. Helpers
remain unavailable until their recorded usage reset; this is not independent
multi-agent review. Scope results establish only the named host observations.
They cannot establish power-loss behavior, physical-space reservation, hard
aggregate quotas, stop latency or capacity for arbitrary future control writes.
