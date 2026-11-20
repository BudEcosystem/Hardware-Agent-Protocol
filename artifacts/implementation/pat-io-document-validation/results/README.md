# Exact-byte document validation results

**292 of 298 distinct methods pass; 6 methods fail.** All 286 control methods pass, including the 19 new canonical-document controls. Each selected method runs once in seventeen retained scopes. All original deadlines, effect/storage budgets, durable writes and complete 30-case group requirements remain unchanged.

The per-engine memo retains only successful validation of complete immutable byte strings, bounded to 64 entries and 128 KiB of key bytes. Original SQL schema/count/type/size checks and current row reads still execute on every snapshot. Changed documents must validate again. Selected parser/encoder dependency changes disable reuse; these compatibility guards are not complete Python-process attestation. No authority, session, permission, source-image verification or physical outcome is cached. Only one inherited production file changes; inherited tests remain byte-identical.

The reserved-worker method now completes all 30 cases, independent inspection and replay after configuration/session changes. A read-only audit joins its one reservation and all 37 documents to the original supervisor request/attempt; replay performs no new planning or second launch. The complete group retains 26 synthetic states, 21 activations, 11 completions, ten cancellations and no claims/owners. This fresh result neither repairs the preceding stage's failures nor proves a deadline guarantee on arbitrary hubs.

The owner-loss-after-settlement case still reaches the supervisor deadline before its planned owner exit. Recovery archives `OWNER_LOST` without a complete return or known exit code. The owner-loss-after-spawn case returns a canonical failed group with `PAT_IO_GROUP_WALL_LIMIT`, retaining 29 completed-case entries of 30. Authority-configured, legacy-configured and PWM cases also reach `SUPERVISOR_DEADLINE` with no return. Their partial states and original leases are retained and inspected read-only; no reset, repair or new logical-key retry occurs. Failed or incomplete groups are not promoted. All failures appear in the exact table and linked audits below.

The PWM failure retains one incomplete state with a transaction journal. Its bytes remain untouched and its logical state is not opened for recovery. Aggregate effects/claims/owners remain unknown. The fifteen inspectable states show ten activations, five completions, five cancellations and zero observed claims/owners; these observations cannot establish totals for the unknown state. The initial generic failure auditor raised a `TypeError` when it encountered the unknown fields. Its [log](../attempt11-pwm-audit-failed-process.log) and the subsequent [partial-state audit](attempt11-failed-pwm/failure-audit.json) are both retained; no test, source, limit or state was changed to obtain that audit.

The archive-commit owner-loss method stops for `SUPERVISOR_RETENTION_UNKNOWN`, a different condition from a deadline. Its pre-exit crash receipt exactly matches the retained archived record, with one worker and no complete return. The original collector maps any retention-scan exception to this reason without recording the exception details; the specific cause cannot be inferred from the terminal inventory. This case also retains fifteen inspectable states with ten activations, five completions and five cancellations, plus one uninspected transaction-bearing state. Overall effect/claim/owner totals remain unknown. Neither the scanner nor its limits was changed in this stage.

| Failed attempt | States | Activations/completions/cancellations | Claims/owners | Completed case entries |
|---|---:|---|---|---|
| [attempt04-crash-settled](attempt04-failed-crash-settled/README.md) | 26 | 19/7/10 | 2/2 | unknown |
| [attempt05-crash-spawned](attempt05-failed-crash-spawned/README.md) | 26 | 17/7/10 | 0/0 | 29 |
| [attempt09-authority-owned](attempt09-failed-authority-owned/README.md) | 20 | 13/6/7 | 1/0 | unknown |
| [attempt10-configured](attempt10-failed-configured/README.md) | 12 | 7/4/3 | 0/0 | unknown |
| [attempt11-pwm](attempt11-failed-pwm/README.md) | 16 | unknown/unknown/unknown | unknown/unknown | unknown |
| [attempt12-crash-archived](attempt12-failed-crash-archived/README.md) | 16 | unknown/unknown/unknown | unknown/unknown | unknown |

The [duplication analysis](../analysis/retained-document-duplication.json) finds 7,768 hypothetical exact-input reuses among 9,000 validations in a preceding retained group. The focused 1,000-repeat observation performs one full validation instead of 1,000, with observed process CPU time about 0.083 s versus 1.013 s. This isolated work observation has no timing acceptance threshold and cannot establish the cause of process deadlines or deployed performance. The [host observation](../analysis/host-capacity-observation.json) describes the observer's visible affinity/cgroup ancestry; it reserves no worker capacity.

Each attempt verifies 248 project files, 251 frozen inputs, six harness files and 159 external pins. Created worker images contain 260 files, including eight supervisor sources and 157 runtime dependencies. Original raw state and exact acquired copies are retained. Primary-agent review only; no physical endpoint, MCU/emulator, live inference/service, acquired controller code or adjacent Harness checkout is used.

| Attempt | Methods | Result | Test seconds |
|---|---:|---|---:|
| [attempt01-canonical19](attempt01-passed-canonical19/README.md) | 19 | passed | 1.16 |
| [attempt02-control206](attempt02-passed-control206/README.md) | 206 | passed | 113.291 |
| [attempt03-reserved-owned](attempt03-passed-reserved-owned/README.md) | 1 | passed | 85.992 |
| [attempt04-crash-settled](attempt04-failed-crash-settled/README.md) | 1 | failed | 70.156 |
| [attempt05-crash-spawned](attempt05-failed-crash-spawned/README.md) | 1 | failed | 76.873 |
| [attempt06-runs15](attempt06-passed-runs15/README.md) | 15 | passed | 166.391 |
| [attempt07-runs14](attempt07-passed-runs14/README.md) | 14 | passed | 88.983 |
| [attempt08-authority32](attempt08-passed-authority32/README.md) | 32 | passed | 79.958 |
| [attempt09-authority-owned](attempt09-failed-authority-owned/README.md) | 1 | failed | 73.163 |
| [attempt10-configured](attempt10-failed-configured/README.md) | 1 | failed | 76.497 |
| [attempt11-pwm](attempt11-failed-pwm/README.md) | 1 | failed | 82.483 |
| [attempt12-crash-archived](attempt12-failed-crash-archived/README.md) | 1 | failed | 58.119 |
| [attempt13-cutoff](attempt13-passed-cutoff/README.md) | 1 | passed | 40.915 |
| [attempt14-pidfd](attempt14-passed-pidfd/README.md) | 1 | passed | 12.198 |
| [attempt15-deadline](attempt15-passed-deadline/README.md) | 1 | passed | 16.7 |
| [attempt16-crash-admitted](attempt16-passed-crash-admitted/README.md) | 1 | passed | 12.4 |
| [attempt17-crash-launching](attempt17-passed-crash-launching/README.md) | 1 | passed | 14.363 |

See the [exact summary](../RESULTS.json), [design](../DESIGN.md) and [next work](../NEXT.md). Durable supervisor-store identity and admission handoff, public service mounting, protected capacity, evidence import/promotion, prompt learning, persistent Arduino applications and real device/driver/hub providers remain unfinished. The full HMS goal remains active.
