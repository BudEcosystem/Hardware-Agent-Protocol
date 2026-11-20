# BHMS final validation — 2026-11-21

This report closes the implementation and verification work in the BHMS build plan. Python and
TypeScript serve protocol `2026-11-15` and retain `2026-11-13` compatibility. The TypeScript port
adds durable cumulative budgets, digest-scoped program grants, version-aware discovery,
standard request credentials, TLS scheme enforcement, duration limits and late-result evidence.
It also fixes policy-envelope validation before program execution and lease-hold terminal outcomes.

The evidence is from simulated devices, host-built C firmware, and the SimLab worker. No BHMS
physical-device commissioning or physical safety qualification was performed. The separately
retained TriAct microscope dossier describes that project's work; it is not BHMS hardware
validation evidence.

## Test suites

| Suite | Result | Evidence |
|---|---|---|
| Python SDK default suite | 1,609 passed; 3 skipped; 2 slow tests deselected | [log](../validation/2026-11-21-final/python-sdk.log) |
| Python slow suite | 2 passed; 1,612 other tests deselected | [log](../validation/2026-11-21-final/python-slow.log) |
| TypeScript SDK | 319 passed, no skipped or failed tests | [log](../validation/2026-11-21-final/typescript.log) |
| C SDK, Debug with ASan/UBSan | 5/5 passed | [log](../validation/2026-11-21-final/c-sdk.log) |
| Actuator firmware, host Debug with ASan/UBSan | 11/11 passed | [log](../validation/2026-11-21-final/actuator-firmware.log) |
| SimLab, current source copied to an isolated worker directory | 242 passed | [log](../validation/2026-11-21-final/simlab.log) |

The slow suite executes every deliberately broken conformance fixture against the full applicable
check set, plus the conformance guide's slow command blocks. Its first run found two stale v0.1
expectations: the version-bypass fixture now also fails the earlier-version behavior check, and
v0.2 core claims have 19 inspection MUST rows rather than 17. Both expectations were corrected;
the complete slow suite then passed.

The default documentation tests ran their executable examples. Two live OpenAI command blocks
were skipped because they require `OPENAI_API_KEY`; the slow conformance blocks skipped by that
run were subsequently exercised by the slow suite. The three Python test skips remain recorded
in the suite output; this report does not treat skips as passes.

## Conformance

All runs below reported zero failed requirements and zero MUST failures. Counts are requirement
results, not unit-test counts. `Skipped` includes inspection requirements that cannot be discharged
by a protocol test. A supported profile with inspection rows is not a complete deployment certification.

| Target | Protocol | Passed requirements | Skipped | Not applicable | Report |
|---|---|---:|---:|---:|---|
| Python multi-principal WebSocket device | v0.2 | 188 | 25 | 8 | [JSON](../validation/2026-11-21-final/py-v02-conformance.json) |
| TypeScript multi-principal WebSocket device | v0.2 | 188 | 25 | 8 | [JSON](../validation/2026-11-21-final/ts-v02-conformance.json) |
| TypeScript multi-principal WebSocket device | v0.1 | 175 | 21 | 25 | [JSON](../validation/2026-11-21-final/ts-v01-conformance.json) |
| TypeScript stdio device | v0.2 | 161 | 24 | 7 | [JSON](../validation/2026-11-21-final/ts-stdio-conformance.json) |
| C host endpoint through compact gateway | v0.2 | 22 | 5 | 0 | [JSON](../validation/2026-11-21-final/compact-conformance.json) |
| Agent bridge | v0.2 | 22 | 1 | 0 | [JSON](../validation/2026-11-21-final/agent-conformance.json) |

The multi-principal runs support core, leases, events, programs, registry, authority and WebSocket
profiles. Core still needs 19 MUST inspection reviews for v0.2 (17 for v0.1). Compact needs four
MUST inspection reviews, including the deployment's exclusive-link assumption. The slow documentation
suite also ran the Python gateway claim successfully.

The JSON reports preserve their actual command and environment metadata. Their implementation commit
field is `unknown`; they were run against this checkout during the consolidation. TypeScript implementation
changes are in `b265465`, `5f696f0`, `6b23787`, `0fe37d5` and `395fb2d`; Python runtime implementation was
unchanged from `f277cef`. The only Python code adjustment in this work updates the expected failures of a
broken test fixture, validated by the slow suite.

## Benchmarks

The [full workstation run](../../bench/results/2026-11-21-final-workstation/summary.json) completed all 13 scenarios
without a scenario error, with **18/20 budget checks passing**. It ran on the Intel i7-10700KF workstation,
ext4/NVMe, Python 3.12.3 and Node 20.20.1, pinned to eight CPUs. The run records shared-host load;
source archival and other validation work overlapped part of the measurement window.

The two failures are B1 median durable-invoke latency with `waitMs=0`: **3.94 ms** versus **3.91 ms**
(fdatasync floor + 1 ms) and **3.86 ms** (SQLite FULL commit floor + 1 ms). Its p99 checks passed.
All B2 non-durable latency, B3 gateway catalog, B4 pagination and B5 compact frame-size checks passed.
The budgets were not relaxed. [Raw verdicts](../../bench/results/2026-11-21-final-workstation/budgets.json),
[scenario output](../validation/2026-11-21-final/benchmark-full.log), and compressed raw samples are retained.

The [focused follow-up](../../bench/results/2026-11-21-final-workstation-quiet/summary.json) ran
`--full --only fsync,invoke` at `1f6f755` after archival/push work finished, with eight CPUs selected
by the idle-CPU sampler. Host load started at 1.20 and rose to 2.5; this was a quieter shared-host
window, not an exclusive machine. Both scenarios completed without errors. B1 still failed:
`waitMs=0` median **5.74 ms**, and `waitMs=1000` median **4.50 ms**, against **4.17 ms** fdatasync
and **4.49 ms** SQLite-based limits. All four B1 p99 and four B2 checks passed. The subset report's
B3–B5 `not measured` entries are expected because those scenarios were deliberately omitted;
the full run above provides their measurements. [Follow-up output](../validation/2026-11-21-final/benchmark-quiet.log)
and [two-run aggregate](../validation/2026-11-21-final/benchmark-aggregate.log) are retained.

B1 therefore remains **FAIL in both final runs under both baselines**. The lower host load did not
remove the miss, so load alone is not an established explanation. Ruling R59 calls for preserving
this outcome, without relaxing the budget. Compact measurements in this run used the native host
endpoint; AVR target execution and physical timing remain unverified.

## Repository consolidation

All ten original worktree branches and `feat/bhms` were already ancestors of the consolidated source.
`main` was fast-forwarded to that history; subsequent fixes and evidence were committed on `main`.
All original branches were pushed, preserving their history.

The original ignore rule excluded historical implementation and verification source under `artifacts/`.
The consolidation includes those source files, accompanying Markdown/SVG documentation, license notices
and build definitions, preserving their paths. The [selection audit](../validation/2026-11-21-final/historical-source-audit.json)
records 233,654 files, 3,428,626,614 bytes across copies and 101,002,743 bytes of unique content.
A [supplementary audit](../validation/2026-11-21-final/historical-source-additional-audit.json)
adds 5,273 patches, type stubs, assembly/include files and supporting sources (35,511,366 bytes),
for **238,927 archived files** in total. These historical snapshots are preserved evidence, not
newly validated or promoted implementations. Generated binaries, captured runtime data, standard
virtual environments, package-install directories and caches remain excluded.

The [repository audit](../validation/2026-11-21-final/repository-audit.json), taken after the source
archive push at `1f6f755`, confirms all 12 local branch tips match their remote branches and are
contained in `main`, all selected historical files are tracked, and there are no stashes. All ten
secondary worktrees have no tracked changes; one contains only a generated autorouter log under
`logs/`. The main checkout's pending files in that snapshot are the README, this report and final
benchmark/validation evidence, committed together in the final documentation commit. No worktree
or branch was deleted, and no history was force-pushed.
