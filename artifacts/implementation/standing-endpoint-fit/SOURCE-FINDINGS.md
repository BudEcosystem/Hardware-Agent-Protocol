# Initial source findings

The sealed parent was revalidated before copying: 762 indexed files, 25437336 bytes, index SHA256 `10d3b5da8b4366511f64331af31ead9cd33b77e679eab106e5732d17d2a505a0`. [parent-revalidation.json](parent-revalidation.json) pins the final native pass and AVR link refusal. The 36 project files are exact copies in `originals/` and initially in `project/`; no compiler, native probe, target or object-inspection tool has been run by this lane.

The retained failed-link map attributes 19364 text bytes to `standing.o`, including 5866 to `hms_standing_handle` and 8002 to `hms_standing_poll`. Source and map review show that many absent helper bodies (`open_record`, `mutation`, `feedback`, `transition`, `evaluate`, `loss_service`) have one source call site. Inlining them is not evidence that their bodies were duplicated. The endian 32/64-bit readers/writers, `fresh`, `account_ok` and `dispatch_report` already have separate emitted bodies. Blanket `noinline` therefore has no established size benefit.

Data-only comparison of the sealed finite map and failed standing map gives `.text` totals 21752 and 43612 bytes, a growth of 21860. Summing placed input `.text`/`.text.*` sections within the output `.text` region gives the following decomposition; discarded sections are excluded.

| Contribution | Change in bytes |
| --- | ---: |
| New `standing.o` | +19364 |
| Common `endpoint.o` | +708 |
| Common `link.o` | +18 |
| Synthetic fixture replacement | +1816 |
| Target composition | +36 |
| Library function sections | -2 |
| Other contributions within output `.text` | -80 |
| Total `.text` growth | +21860 |

Clock, EEPROM, boot, RX, TX and runtime function-section totals are unchanged. The linked wide arithmetic helper bodies are already present in the finite image: add/subtract/compare bodies are 18 bytes each and the signed-small variants 24. Controller call sites, argument movement, spills and control flow therefore require inspection; a newly introduced large arithmetic library does not explain the growth. The additional 8 bytes of `.data` account for the remaining difference in total flash load. This decomposition concerns placed map sections, not execution or a valid final standing ELF.

Three narrow investigations precede any wider refactor:

1. `standing_fixture.c:finite_describe` assigns a constant primitive descriptor with one 32-bit and four byte fields. Root's retained object inspection confirms the eight-byte copy loop and `.rodata` relocations; bytes `e8030000 03200100` match the exact descriptor. The new candidate uses explicit stores to the same five fields. Generated storage still needs measurement. See [fixture disassembly](../../verification/standing-size-analysis/attempt01/standing-fixture-disassembly.stdout) and [constant bytes](../../verification/standing-size-analysis/attempt01/fixture-constant-bytes.stdout).
2. `standing.c:feedback` computed a signed 64-bit difference between the accepted pre-dispatch demand baseline and current accepted demand. Both originate from channel-0 samples accepted only in [-100000,200000]. A pending ordinary feedback evaluation follows accepted dispatch; the baseline is overwritten before such feedback uses it. The reachable difference lies in [-300000,300000], so the new candidate uses a signed 32-bit calculation under the existing no-external-mutation contract. This does not justify narrowing any timestamp, lease, conservation accumulator or arbitrary signed wire field. Actual flash/stack effects remain unmeasured.
3. `ri32` and `cancel_pending` have multiple source call sites but no standalone map body. `ri32` may already reduce to the existing `r32` call, while `cancel_pending` is small and used twice. Root object inspection can distinguish actual repeated code from an optimizer simplification. No flash saving from outlining either is assumed.

`fresh` and `accept_observation` also share a pure predicate: acquisition is not ABSENT, is no later than current time, and has age strictly less than its bound. A later helper experiment could preserve this exactly while leaving sample monotonicity separate. Lease-window arithmetic, dispatch cutoff saturation, strictly post-handoff loss evidence and conservation through confirmed quiescence have different boundaries and must not be collapsed into that predicate.

Coverage for these findings: the current complete `standing.c`, `standing.h`, `endpoint.c`, relevant `endpoint.h` descriptor/storage definitions, complete synthetic fixture and target, retained map/`.su` evidence and selected runner freeze/build/resource sections. Full indexed hash verification is not a claim that every indexed file was read as source. Child review independently read the standing controller/header and map/stack records. Object disassembly and any new build remain separate root-owned work.

The evidence supports small measurable experiments, not recovery of the full 10878-byte physical flash overflow. All existing wire, shared authority, lifecycle, callback order, evidence, storage and target budgets remain requirements.
