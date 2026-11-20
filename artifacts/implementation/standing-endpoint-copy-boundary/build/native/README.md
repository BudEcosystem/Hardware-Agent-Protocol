# Encoded timestamp copies and finite-poll boundary

Source-only successor to the sealed standing LTO candidate. No compiler, candidate import, probe, test, emulator or device has run in this lane. A future runner is prepared as source and awaits root review; it has not been imported or invoked. The previous failed LTO link remains the latest target result: 41,892 flash bytes, 9,124 bytes beyond the physical ATmega328P flash region; runtime fit is unsupported.

The candidate changes seven encoded eight-byte read/write roundtrips to `memmove`, twelve constant absent-time writes to `memset`, and gives only `poll_finite` a conditional GNU `noinline` attribute. One new controller control exercises two complete high-timestamp timelines. All 13 previous controls remain, for 14 proposed cases; none has run against these changes.

| Review input | Purpose |
| --- | --- |
| [REVIEW.md](REVIEW.md) | Exact substitution scope, overlap and ordering proof, compiler boundary limits |
| [CONTROLS.md](CONTROLS.md) | New timeline oracle and required later regression/generated-code checks |
| [PLAN.md](PLAN.md) | Bounded next stages, requiring root review before execution |
| [project.diff](project.diff) | Complete changes from the frozen current LTO C source |
| [project-source-review.json](project-source-review.json) | Current project and review hashes; source-only status |
| [source-pins.json](source-pins.json) | Revalidated sealed inputs, 36 exact baseline files and retained snapshots |
| [SOURCE-COVERAGE.md](SOURCE-COVERAGE.md) | Exact source/data reading scope |
| [RUNNER-REVIEW.md](RUNNER-REVIEW.md), [runner-diff.patch](runner-diff.patch) | Complete proposed runner delta from corrected sealed LTO runner |
| [PROFILE.md](PROFILE.md), [native-coverage.json](native-coverage.json) | Unchanged target/tool profile and retained native coverage gates |
| [WIRE.md](WIRE.md), [retention.json](retention.json) | Unchanged wire profile and exact parent root/storage policy |

`originals/project/` retains all 36 baseline files exactly. `project/` changes only `protocol/endpoint/standing.c`, `protocol/endpoint/endpoint.c` and `tests/standing_controls.c`. `inputs/` contains point-in-time parent/research evidence, not a new execution receipt. Public files and all sealed parents remain untouched.

The exact root-reviewed 93-file source proposal, including review hash `e8b3e4a256425b6d860f29e268b46940063fcfd584285db6376b17c26307e647`, is preserved under `history/source-proposal/`. Its index hash is `f2387700d92b528162376291ad01d6a9ceca6b2d53f05c8cc01fb51fe681f253`. Subsequent additions are runner preparation and metadata only; the three reviewed project changes remain byte-identical.

The target remains ATmega328P at 16 MHz, physical 32,768-byte flash/2,048-byte SRAM, 32,256-byte application flash ceiling, 512-byte stack reservation, maximum 160-byte static growth over the 1,343-byte finite baseline, and the existing 128-byte controller/32-byte glue/256-byte arena accounting. No claimed savings, target-fit result, combined stack proof or physical qualification follows from this source proposal.
