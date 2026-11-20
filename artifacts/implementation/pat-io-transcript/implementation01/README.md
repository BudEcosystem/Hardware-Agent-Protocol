# Independent finite-I/O transcript reader candidate

This isolated candidate adds a pure transcript reader and 39 tests. The 159
inherited project files remain byte-identical to the phase-engine candidate.
Copied data contains all nineteen actual trial states' 2,619 records and manifests,
acquired from the sealed trial20 result. No simulator or research code is executed
by preparation or by these data-driven tests.

The reader imports only shared bounded canonical JSON contracts plus standard
library hashing/regular expressions. It imports no worker, I/O provider, runtime
or fan outcome reducer. After normal contract-module startup, inspection performs
no file, clock, database, network or provider calls. Its caller supplies acquired
bytes and separately trusted setup; the reader never opens paths from records.

The closed grammar checks all 29 table inventories and their fixed columns,
SQLite scalar tags, canonical embedded JSON bytes, row ceilings, page continuity,
primary keys, ordering, backward references and complete consumption. It enforces
4,096 records, 64 KiB per document, 16 MiB aggregate input bytes and 2,048 drive
calls. Calls require before/start/return-or-failure/after phases. Reopen requires
the same authority, the next owner epoch and a fresh session; checkpoint clock
epochs and virtual-time changes must agree. The emitted plan must equal the
recorded compiler return. Accounting includes every record and byte before an
observation. A complete transcript ends at the retained final checkpoint/report.

Tests use all nineteen original outputs, exercise the sixteen-step multi-page
case, and rehash adversarial page/table/key/type/phase/clock/session/plan mutations.
The reader must preserve the distinction between structural acceptance and a
successful outcome: the missing-receipt transcript can be structurally complete
while reporting an unresolved operation. No qualification flag is set true.

This is the evidence-reader portion of the independent reducer, not a complete
effect oracle. Receipt/intent/proof associations, independent GPIO/PWM footprints
and states, counter histories, operation/event/replay semantics, complete live
configuration attestation and final settlement still require semantic reduction.
Record hashes and trusted producer provenance do not prove physical execution.
The setup fixtures are trusted historical data for tests; this candidate does not
reconstruct or qualify those historical driver/compiler identities as current.

Source preparation is static only. Actual executions and failures must be retained
separately. The live HMS runtime, previous source/result seals, adjacent Harness
checkout and physical devices remain unchanged. Independent agent review is
unavailable because the helper agents reached their account usage limit.
