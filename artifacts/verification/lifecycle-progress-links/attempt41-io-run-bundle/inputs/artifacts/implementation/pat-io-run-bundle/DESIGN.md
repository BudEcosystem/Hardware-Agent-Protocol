# Bounded pre-run I/O bundle

The current supervisor accepts one canonical document of at most 65,536 bytes.
The complete I/O setup requires six input documents and thirty expected-case
documents. This component adds a separately bounded header and the original
authority as a seventh fixed input, before adapting the process supervisor.

The builder calls the existing trusted setup generator. Its result contains a
header, an exact mapping of canonical document bytes, and a domain-separated
header digest. Fixed paths are `inputs/{candidate,installation,descriptor,
bindings,matrix,implementation,authority}.json` and `cases/00.json` through at
most `cases/31.json`. The ordered manifest binds each path, size and SHA-256.
The input-set digest covers the ordered manifest; the bundle digest covers the
complete header including deployment, evaluator, logical run and configuration
reference. The logical run is separate from any supervisor-generated attempt ID.
No caller-supplied path, executable, PID or signal is part of this contract.

There are at most 39 input documents, each at most 65,536 bytes, for a maximum
2,555,904 input bytes. The header has its own 65,536-byte bound. These bytes must
be charged alongside source images, output, streams and control records within
the supervisor's existing attempt reservation. No group ceiling changes: 32
cases, 512 operations, 2,048 ticks, 4,096 records, 16 MiB producer bytes, 20 MiB
derived bytes and 60 seconds. A logical byte bound is not a filesystem quota.

The parser requires a separately retained expected bundle digest and logical
context. They must come from the trusted admission record, not the worker's
returned archive. It checks exact document closure/order, canonical bytes,
strict types, bounds and input/case associations. It does not invoke a planner,
worker, database or clock, or read files during parsing. Importing the shared
contracts module retains its existing installed schema-loading behavior.

Structural agreement is deliberately separate from a fresh rebuild. The latter
calls the existing setup generator using the supplied candidate, installation,
descriptors, original authority and limits, rechecks current source identities,
and requires every reconstructed byte to match. Tests show that fully rehashed
false setup and changed original authority can satisfy the structural layer if
the caller replaces its trust anchor, but fail fresh reconstruction.

Neither layer attests the provenance or current authority of its supplied
configuration reference. Durable admission, protected input retention before
release, trusted service configuration, owned child/process association,
complete output collection, real aggregate storage enforcement and public
qualification remain separate work. No qualification or physical result is
claimed by the bundle.

Source01 adds one production module and nineteen tests. Every one of the 228
inherited project files remains byte-identical. The original 129 pure methods
plus the nineteen new methods are selected in one bounded, isolated harness.
The new methods include GPIO/PWM reconstruction, retained example documents,
cross-run/configuration substitution, hash/closure/canonical/type bounds, pure
parser guards, changed authority and installed source checks. No SQLite
connection or device execution is authorized for this selection.

Review is by the primary agent; helper execution remains unavailable under the
reported usage limit. No independent review is claimed. Initial preparation
tried the unavailable `python` command and made no filesystem changes; the
reviewed copy operation then used `python3`.

The current source03 selection contains149methods: the original129 and20new
bundle checks. Source02 corrects one test's imported-function patch lookup;
source03 moves exact key-type validation before path-set hashing and adds the
corresponding rejected-hook regression. See [results](results/README.md),
[test correction](CORRECTION.md), [key guard](KEY-GUARD.md) and
[reporting correction](ANALYSIS-CORRECTION.md). All original228baseline files
remain unchanged; current driver/worker digests reflect the additive module.
