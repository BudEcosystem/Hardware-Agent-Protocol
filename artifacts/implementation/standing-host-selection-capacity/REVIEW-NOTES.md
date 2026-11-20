# Exact source changes for review

`project/` contains 259 files exactly copied from sealed selection-reuse. Its
only historically changed production module remains standing_pat.py SHA
9205c5482c38399d90c55b88deacaf009874d0f3f823a0834bd3d0b477afda4e.
No project file is modified here. `source-pins.json` records all 262 unchanged
reuse joins and 18 original provenance joins; PREPARATION-REVALIDATION.json
records this source/data-only revalidation, not candidate execution.

`boundary_controls.py` is the exact sealed original source SHA
01e91d85d9da351af7f1c8dc8cd42bf375898959ff1264754408311042517e5d.
The new wrapper imports it only after checking that fixed pin. Its complete
`mutation_capacity` body, helpers, faults and assertions remain unchanged.
Only that fixed function is called; the other original profiles/main are not
selected. No global production method, parser or encoder is monkeypatched.
The wrapper's only subclass adds a bounded trace check before delegating the
same checkpoint, result and exception behavior.

`capacity_controls.py` is new. It uses the reviewed strict stdlib JSON receipt
pattern, retains all 28 selectors and original trace, joins clean child identity
and exit, checks released leases, and publishes failure-safe receipts with
masked cleanup and deferred-signal correction. Memory-only failure diagnostics
are explicitly partial. A passing assembly requires the original complete case
plus retained 120/126/128 notes and 128 actual mutation rows with zero claims.

`runner.patch` is the exact delta from the sealed selection-reuse runner.
It narrows invocation to mutation, swaps in the exact sealed capacity Guardian,
selects the preexisting 32 MiB control file profile, verifies the three relevant
parents and106 receipt, and reduces the full original case evidence. It retains
exclusive explicit attempts, held executable checks, process limits, original
ownership and cleanup. It reads a bounded inner receipt after process completion
even if exit is nonzero, and distinguishes a missing receipt from zero counts.
This is evidence reporting; failure never becomes success through cleanup.

`guardian-variant.patch` shows the already sealed boundary Guardian difference
from the selection-reuse Guardian. The current file is an exact existing copy,
not a new ownership implementation. The exact helper remains SHA
a6ee94bcf3dc03df19f0dd07a81663badd4875ef1a6c429afbc55d7b2373b977.
No helper compilation or native qualification execution is needed or performed.

The new source has not been imported, executed or compiled. Root's full review,
source freeze verification and fixed execution remain pending. Current proof is
limited to exact source/copy joins and the preserved historical evidence.
