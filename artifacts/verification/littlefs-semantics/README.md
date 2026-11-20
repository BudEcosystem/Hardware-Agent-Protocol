# littlefs host semantic observations

Stage 83, 2026-11-09. **Four bounded RAM scopes completed successfully**, plus a
fresh local POSIX descriptor comparison. This is suitability evidence, not a
qualified filesystem or storage service. [Raw result](attempt01/observations.json),
[plan](PLAN.md), [review](REVIEW.md), [source reading](../../../research/host-contract/littlefs-core/README.md).

| Observation | Retained result | Implication |
|---|---|---|
| First 4 KiB overwritten in a 256 KiB file | 262,688 program bytes; 65 erases | Suffix COW dominates this update |
| Final 4 KiB overwritten in the same-sized file | 4,640 program bytes; two erases | Cost depends strongly on offset |
| Existing reader after another handle syncs B | Existing reader A; fresh reader B | Direct independent handles are not coherent POSIX descriptors |
| Pending write followed by unmount/remount | Zero unmount sync calls; earlier A retained | Unmount is release-only; drain/sync is explicit |
| Native POSIX comparison | Existing descriptor reads B | Records the expected local coherence behavior |

The two overwrite scopes verify every byte of the resulting file, not just the
changed region. Each littlefs scope uses a fresh 2 MiB RAM device, 4 KiB blocks,
16-byte program/read units, 256-byte caches and a 64-byte lookahead bitmap. Inline
files and wear relocation are disabled. Each retains a 2 MiB research image;
the four images total 8 MiB. RAM sync is a counter, so it proves no durability.

The fully read pinned core and utility implementation compile with GCC 13.3.0,
C11, O2, warnings as errors, assertions enabled and LFS_NO_MALLOC. Only original
probe code and these selected acquired files execute; no upstream build/test
scripts execute. Each child has the declared wall, CPU, address-space, file-size
and descriptor limits. Raw intents, PIDs, terminal results and logs are retained.
No failed or retried scope occurred. The research harness itself is not a
crash-qualified service supervisor.

Nine exact inputs are frozen. Compiler/binary/source identities and all 244 public
runtime inputs match their expected values after execution. The previous public
866-test passing receipt still applies to unchanged runtime sources; that full
suite and the thirty-case worker were not repeated.

**Decision:** reject the direct handle mapping. [Design](DESIGN.md) selects a
bounded chunked adapter as the next candidate, with shared inode state and explicit
ownership/recovery. No SQLite, FUSE integration, physical flash, power loss, backed
continuation capacity or total service quota is qualified here. Endpoint immutable
PAT storage and hub random-write databases may use different provider profiles.

[Audit](AUDIT.json) and [exact inventory](index.json) retain the evidence.
[Next work](NEXT.md) preserves the complete device/driver/hub and prompt-to-PAT goal.
