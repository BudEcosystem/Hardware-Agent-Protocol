# Remaining worker cost: source review

The current diagnostic measures 35.853978 seconds of waited-worker CPU and
10.794492 seconds of supervisor CPU during an approximately 60.041-second
launch/reap interval. It measures neither per-function time nor a waiting cause.
Subtracting CPU from elapsed time cannot identify filesystem, scheduler or other
delay, and summing parent/child CPU does not yield their elapsed critical path.

The retained earlier profiler supplies a separate, interrupted observation:
7,862 canonicalizations, 630,079 recursive JCS encoder calls, 697 explicit fsync
calls and 27,810 SQLite execute calls. Its cumulative times overlap, and its
instrumentation, earlier source and smaller completed prefix differ from the
current trial. It is evidence for choosing investigations, not a current timing
estimate. The exact profile copy and source-reading hashes are in
[path-review-inputs.json](path-review-inputs.json).

Current `synthetic_io_installation.py` already memoizes pure normalization after
fresh source checks and shares topology work within one definitions build.
`implementation_digest()` still rereads the conservative source closure. Replacing
that with a cross-call identity cache would remove an existing freshness check.
No such change is proposed.

Current `pat_io_trials.py` already uses `PageEncodings` for reusable table pages.
Each new record checks budgets, writes and fsyncs before publishing its reference.
Capture rereads bounded table shape, row counts, sizes and values while holding
the runtime owners. Group capture writes every original case manifest and checks
implementation identities again before its complete return. Removing durability,
snapshot or final identity checks is not a supported optimization.

The next bounded evaluation can target integer-only canonical serialization.
Keep `check_tree`, refusal order, exact-type rules, numeric/depth/node/string/output
limits and the original floating-point encoder. After validation, an internal
fast path could build dictionaries in UTF-16 key order and use the standard
library encoder for trees containing only exact integers, booleans, null and
strings. Any float must use the original RFC 8785 implementation for the entire
value. Ordinary Unicode code-point sorting or Python's default float formatting
would not preserve JCS identity.

This is a proposal only. First compare exact bytes and refusals with the original
implementation over retained bounded worker documents and adversarial cases:
UTF-16 ordering across BMP/supplementary characters, all control escapes, valid
Unicode, lone surrogates, safe-integer edges, floats and negative zero, cycles,
aliases, custom types and the size/depth/node boundaries. Verify public helper
replacement behavior and detached results where relevant. Fixed interleaved
measurements must justify adoption; a small or inconsistent gain is insufficient.
Do not import project/controller code merely to inspect retained documents.

No serializer, worker, deadline, matrix or production module changes in this
stage. If the evaluation succeeds, it still requires fresh identities and the
complete original qualification/import scope before adoption.
