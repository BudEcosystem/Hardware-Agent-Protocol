# Guarded integer canonicalization in the isolated host

The [pure evaluation](../../verification/pat-integer-canonical-evaluation/README.md)
passes 1,668 differential cases and measures lower CPU cost in all nine fixed
pairs. This supplies evidence for a fresh integration trial. It does not prove
that the original worker deadline will be met.

The candidate changes `hms/contracts.py` only: its original `canonical` validation,
error wrapping and final length check remain, and its byte-generation call selects
the exact evaluated helper. All original parser/validation functions and the new
helper functions are AST-checked against their frozen references. The helper file's
evaluation-only docstring is omitted when inserting its nodes into the module.
The original test's literal consumer pin is the second changed inherited file.
All 289 remaining inherited project files are byte-identical.

Integer-only input gets fresh containers ordered by UTF-16 key bytes. Any float
uses the original RFC 8785 encoder for the whole value. The fast path observes
selected helper, code/default, constant, escape-table and standard-library encoder
guards. It does not cache input trees or current implementation identities, change
the source/authority checks, remove fsyncs or weaken capture/publication semantics.
Input containers are not modified. Arbitrary interpreter tampering and concurrent
mutation of caller-owned values are not newly qualified behaviors.

The exact 291-file project is frozen with independently recomputed legacy, vault
and authority-consumer identities, using ASCII-key identity envelopes outside
project execution. Producer-image inventory remains 265 files; the native scanner
binary and supervisor are unchanged. Normal imports of the candidate pass all
nine inherited public contract tests with selected source origins checked and
process/network/database effects refused. Retained intent digest fixtures match.

The [execution harness](harness01/SCOPE.md) preserves the byte-identical native
guard and original-process observer from the preceding diagnostic. Only source
selection, source index and scratch prefix change in its parent. The original
thirty-case worker, actual semantic reducer/import and cold-vault history test
remain unchanged apart from the consumer pin. Worker/parent limits remain 60/180
seconds; all original file, scratch, snapshot, vault and effect bounds remain.

The candidate is isolated; the public runtime is unchanged. Success or failure
must be established from the original terminal receipt and a retained-state audit.
No result here can substitute for catalog integration, backed control capacity,
full public qualification, validated learning or physical I/O/driver/hub providers.
