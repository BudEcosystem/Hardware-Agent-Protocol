# Independent multi-adapter review

The final reviewed revision has no blocking semantic finding within the installed synthetic-adapter contract. Nine independent Python/SQLite cases passed, and an isolated real-clock run completed all nine scenarios across one local plant and two original native C endpoint fixtures. The final source set was checked before and after execution. `review.json` records hashes and qualifications; `verify.py` verifies the receipt offline without running a fixture.

## Findings and repairs

An existing empty local plant database originally raised an untranslated `sqlite3.OperationalError` and prevented healthy routes from opening. `SimulatedPlant` now translates SQLite initialization errors into `INVALID_SIMULATED_PLANT`; multi-route startup mounts that installation as unavailable. The independent probe tested both an empty file and non-SQLite bytes, completed work on the healthy route, and verified that the damaged bytes were unchanged.

Separate durable ingress transactions and idle clock-floor writes caused measured freshness failures. The final revision batches each adapter snapshot, uses one pre-mutation wall-clock origin for its presence records, preserves observation acquisition age, commits stream caches only after successful ingress, and holds the shared authority mutex across compact refresh. Idle routes without accepted work skip unnecessary clock-floor commits. Freshness and clock-bracket bounds were not widened.

The following failed runs remain evidence, rather than being replaced by the passing run:

| Record | Revision / condition | First failure |
| --- | --- | --- |
| `realtime-before-batched-ingress.json` | Pre-batch diagnostic; exact source hashes were not captured | `OBSERVATION_STALE`, first compact prepare after three local completions |
| `realtime-batched-concurrent-load.json` | Batch revision, before refresh mutex; pinned by `sources-before-refresh-lock.json`; ran with root validation | `DEVICE_UNAVAILABLE`, first compact prepare after three local completions |
| `realtime-refresh-lock-concurrent-load.json` | Final source pins; ran with targeted validation and independent probes | `OBSERVATION_STALE`, first compact prepare after three local completions |
| `realtime-diagnostic.json` | Final source pins; other review/root test processes paused | Nine completed operations, no admission retries |

In the final concurrent-load failure, the compact sample's conservative age was 1,475 ms, including 255 ms acquisition-to-publication latency. No route error or compact fault was recorded at that point. The refresh lock tightened the acquisition bracket; it does not ensure a bounded refresh cadence. The isolated pass establishes the observed scenario result, not a benchmark or availability guarantee under load. User processes were not stopped or changed.

## Review scope

The code review covered installation identity and catalog immutability, generated plant filenames and path checks, partial startup, historical operation routing, route filtering before limits, global resource claims, per-route faults and packet state, schema migration, read/transaction locking, atomic ingress, clock serialization, result replay, and absence of automatic OP replay after loss of support. The reviewed implementation files are listed in `review.json`; the larger pinned source set includes supporting modules and tests that are not all claimed as independently line-reviewed.

An additional read-only reviewer checked registry/journal admission, replay, resources, binding history, and the final ingress/refresh changes. A suspected dispute/restore interleaving was reassessed: the only production call to `_restore_samples` is under the newly held authority mutex, so the hypothesized gap is not reachable through the production refresh path. Calling that private helper directly does not reproduce production locking.

The nine original independent cases cover:

- Advancing wall time on every clock callback, with one expiry origin per snapshot.
- A late invalid observation rolling back sessions, presence, streams, history, and observations while preserving the observed wall-clock floor; RAM stream counters stay unchanged until commit.
- Acquisition-to-publication delay plus later read delay in the conservative observation age.
- Empty and malformed store isolation without replacement or formatting.
- Offline compact counter reservation and fault isolation while a local operation is running.
- Historical result/replay routing after the current binding changes to another adapter.
- Exact opaque byte and row-ID preservation during legacy endpoint schema migration, including idempotence.
- Migration rollback after a deliberately denied late `DROP TABLE`.
- Rejection of incomplete and mixed-route-column schemas without mutation.

The in-memory migration fixture exercises the schema function with retained opaque bytes; it is not a complete legacy runtime lifecycle test. Route-global resource and SQL filtering invariants were source-reviewed; broader integration coverage belongs to the main implementation suite. The first startup-failure JSON is a retained early observation without a frozen pre-fix source receipt.

## Boundaries

These are original host simulations and SQLite tests. No hardware, AVR target, emulator, downloaded controller, or downloaded cryptographic implementation was executed. The native fixture was checked against its retained producer binary hash before launch. Its existing same-host clock profile is a supplied simulation assumption, not physical clock qualification.

Per-route workers still share the authority mutex, durable SQLite commits, and host resources. Compact refresh and ARM can delay other routes. No timing isolation, electrical behavior, baud timing, physical actuation, crash-proof storage hardware, or general hostile-device qualification is claimed. The early load failures remain compatible with fail-closed freshness checks and constrain availability claims.

Run `python3 artifacts/verification/multi-adapter-code-review/verify.py` to check retained evidence and current source equality. `--retained-only` checks the frozen record after live development has advanced. Reproduction commands for the executed probes are in `review.json`; rerunning the live diagnostic requires the already-built original host fixture and a quiet test workload.
