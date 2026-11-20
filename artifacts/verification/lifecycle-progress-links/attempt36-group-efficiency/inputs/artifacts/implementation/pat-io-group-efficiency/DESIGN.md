# Exact plan reuse and compact fresh synthetic stores

The [preceding attempt](../pat-io-schema-memo/results/README.md) completed 25 of 30
cases at its original deadline and retained 16,324,409 bytes, near the 16 MiB
harness ceiling. Its profile measured repeated full matrix construction; its
read-only storage audit found 7,123,390 unused bytes within SQLite pages.

`ValidatedIoMatrix` constructs and validates the complete original matrix once.
It holds detached bounded copies of the five associated documents. Each fixed
case uses its active, unbound group ticket to compare the supplied candidate,
installation, descriptor, challenge bindings and matrix against that bundle.
The existing type-sensitive tree comparison distinguishes integers, booleans and
integral floats. Reuse performs no filesystem or authority access and retains
no caller data. All standalone runners still reconstruct and validate the full
matrix. Runtime setup still normalizes the installation and rechecks source
identity; every binding, permission, claim and effect guard remains. This trusted
in-process object is not a wire credential, deployment attestor or defense against
arbitrary in-process code mutation.

The three original synthetic worker runtime-open paths now explicitly select
`hms.sqlite.compact/0.1`. That closed profile chooses 1024-byte pages only before
schema creation in a fresh authority/board database. Opening with that profile
requires the existing page size to match and never converts a database. Ordinary
runtime callers retain the default profile; they may reopen existing compact
files without converting them. SQL schemas, transactions, DELETE journaling,
EXTRA synchronization, ownership, receipts and recovery remain unchanged. The
selected worker profile is retained in group identity evidence and the changed
source is included in the installed implementation digest. No old retained
database is opened for mutation, vacuumed, reset, compressed or removed.

SQLite documents 1024 bytes as a supported page size and specifies that a changed
size applies on initial creation or a subsequent VACUUM. The existing project
[local primary source](../../../research/host-contract/text/sqlite-pragmas.txt)
and the [official page-size documentation](https://www.sqlite.org/pragma.html#pragma_page_size)
were consulted for this narrow change; the official page was checked on 2026-11-07.
The default remains recommended for most applications. This profile is an
explicit measured synthetic workload choice, not a universal performance claim.
Successful setting checks, rollback and owner-reopen tests do not prove real
power-loss durability or establish an aggregate disk quota.

Validation selects 87 pure methods, six actual compact/default-store tests, the
actual 250-record cutoff and separate unchanged full GPIO/PWM groups. New cases
exercise exact association for every document, numeric types, detached outputs,
stale/bound tickets, all five runner families and unchanged standalone refusals.
Storage tests check actual headers, integrity and durability settings, rollback,
owner exclusion, mismatch without file rewrite, pending recovery and same-key
replay after reopen. Full groups still require every 30 cases, all 25 fixed
challenges, 28 actual child operations, exact evidence accounting and 52 retained
databases; they additionally check the selected page layout.

No case, schedule, fault, logical row, evidence field or existing bound is removed
or relaxed. Original 32 cases, 512 operations, 2048 ticks, 4096 records, 16 MiB producer,
64 KiB documents, 20 MiB derived and 60s group limits remain, as do 180s harness and
16 MiB retained-scratch limits. Full independent outcomes, trusted setup/run
association, actual aggregate storage, supervision and public qualification still
follow capture. Persistent applications, agent learning, physical I/O and
intelligence-hub lifecycle/compute providers remain part of the complete goal.
