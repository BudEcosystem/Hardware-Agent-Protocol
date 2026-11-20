# Native scanner in the qualification supervisor

The fresh isolated supervisor loads and uses the native scanner, but the complete
worker/import scope still fails at its original deadline. **No whole-worker
performance improvement or successful qualification is established.** The
[audit](RESULTS.json) verifies the failed scope and its retained state.

The [current source](implementation02/README.md) adds a strict Python wrapper and
the unchanged original C source/DSO to the supervisor's source and producer-image
identities. Verified bytes are copied into a sealed Linux memfd before dynamic
loading. The loader owns one close-on-exec descriptor for process lifetime and
does not retry a failed load. It honors kernel executable-memfd policy. The
[design](DESIGN.md) states the exact profile, input differences and limitations.

All [six fresh loader scopes](controls02/result.json) pass, with thirteen grouped
checks. They cover normal Python import, input bounds, error mapping, kernel seal
enforcement through multiple descriptors, thirty reuses, on-disk replacement after
verification, digest refusal, audit veto and bounded failed-load behavior. The
[sixteen guard controls](guard-controls02.json) exercise the exact embedded audit
code with an owned sealed image and out-of-scope path/digest/limit cases.

The [actual test](harness02/attempts/attempt01-actual/result.json) requests all
thirty cases under the original 60-second worker and 180-second parent bounds.
It leaves sixteen case directories and fifteen manifests; `run_completion_equal`
is interrupted. The supervisor records deadline termination with exit code -15,
no complete return, and unknown unresolved effects. Import and publication are
not reached. The test-body checkpoints show 60,161 ms from spawn to settlement;
the parent scope takes 123.238 seconds. These are not matched performance samples.

The native guard records one supervisor-root scan and 2,286 attempt scans, one
load and one held image. The child's final origin check verifies the sealed image
against the acquired DSO and records 876 origins without violations. The later
audit does not reopen the terminated child's numeric descriptor path. It verifies
1,927 retained files / 11,352,470 bytes, all 265 producer-image files, and four
unchanged source databases under 29 original owner/writer locks. No interrupted
case database is opened or recovered. The installed vault remains empty and the
source authority has no imports, publications, operations or resource claims.

The [first actual attempt](harness01/attempts/attempt01-actual/result.json) failed
during import: `retention_native.so` shadowed `retention_native.py`. It launched no
qualification worker and opened no database. Its exact source, harness and empty
scratch capture remain intact. The current fresh candidate names the binary
`retention_scan.so` and exercises ordinary import in its controls. Two earlier
preparation failures are also retained: unsorted identity-reproduction input and
missing explicit distribution roots. The successful preparation sorts identity
rows and reads the pinned distribution metadata directly; source package code is
not imported to calculate those pins.

The [primary-source packet](../../../research/host-contract/native-loader/README.md)
contains 836 fully read LF lines. Earlier CPython API reading remains partial.
Review was by the primary agent. Public runtime, physical providers, Arduino
firmware and the adjacent Harness checkout are unchanged. [Next work](NEXT.md)
preserves the full goal and does not rerun an unchanged trial as a deadline fix.
