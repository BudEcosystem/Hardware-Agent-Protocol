# Owned host CPU-job control results

The root executed the reviewed isolated candidate in three separate preserved attempts. All three returned success. This is the current result note; README, DESIGN and PLAN retain their reviewed pre-execution wording as exact frozen inputs. The provider reviewer inspected the retained result receipts read-only; the reviewer did not execute the candidate. The original public runtime and its simulation selection were not modified.

| Attempt | Observed checks | Control elapsed seconds | Result |
| --- | ---: | ---: | --- |
| `structural-attempt-1` | 23 | 0.062815 | Passed |
| `live-attempt-1` | 94 | 2.305908 | Passed |
| `faults-attempt-1` | 92 | 1.863157 | Passed |

These are 209 observed assertion checks, not 209 distinct test scenarios. In particular, the writer-lingers observation adds checks during polling, so the count can vary with scheduling. Each attempt retains frozen source/helper bytes, source pins, stdout/stderr, process observations, interpreter observations and public-baseline observations. Each `RESULTS.json` reports `sourceStable`, `interpreterStable` and `publicBaselineStable` true, an owned control leader reaped with exit zero, no pending cleanup interrupts and no remaining observed live process. `abnormalOwnerCrashQualified` remains false in all three receipts.

The exact prior receipt `artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json`, SHA256 `dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e`, and its 244 file hashes matched before and after each group. The prior 866-test suite was not rerun. These are sequential hash observations; they do not detect a transient change followed by restoration.

The live group retained thirteen terminal job rows. It exercised actual installed integer-series CPU work and strict output validation, original-key replay/conflict, active capacity, simulated source-read drift, owner-thread refusal, cancellation before and after gate release, a delayed release-intent boundary whose expired budget withheld the gate byte, invalid output variants, stream overflow and a descendant retaining its writer lease/streams while the leader waited. The late gate check preserved conservative `mayHaveActed=true` after committed release intent even though the control observed no gate byte written.

The faults group retained thirteen terminal job rows and an empty SIGCHLD-refusal ledger. It exercised ten checkpoint exceptions, failed pidfd acquisition, refusal under explicit SIGCHLD ignore, a pending SIGINT at child registration, and a pending SIGINT between reaping and publication. The checkpoint controls retained and settled original live handles before reopening. They establish orderly fault behavior for the executed boundaries, not recovery from the death of the owner process.

The structural group exercised strict request/result types, negative sealed-memfd write/truncate controls, original-key and terminal immutability, strict receipt counters/reasons and cross-slot successor validation. Its deliberately invalid rollback ledger is an expected refusal fixture. No caller-provided shell, executable, path, module or test mode entered the job API.

The process evidence is limited. `/proc` observations are bounded snapshots and can miss short-lived descendants. A recorded state describes a prior observation, not the current presence of that process. The receipts distinguish PID/start-tick identities during final observation. Empty remaining-live observations and outer control-group cleanup do not prove universal descendant enumeration or reaping. Separate-session jobs remain outside the outer control group's containment. The installed worker's lease discipline and fixed one-child behavior are trusted code contracts, not sandbox enforcement.

The root's separate [retained-data audit](ROOT-AUDIT.json) passed using original [audit source](audit_retained.py), with no candidate module imports or worker execution. It checks all 57 snapshot slots, 26 live/fault terminal records and one structural terminal fixture, while recognizing the intentionally invalid successor fixture separately. It independently sums all six successful 1,000-term arithmetic results, acquires all 25 matching free writer leases through read-only descriptors, and confirms that all 29 process identities found in control/receipt observations are absent, including zombies. All retained attempt bytes remain exact. This does not claim that bounded snapshots enumerate every short-lived descendant. The earlier native signal-query helper's six cases/twelve checks remain separate evidence, not additional job scenarios.

Limits remain per process, and wall/settlement enforcement depends on serviced polling. There is no aggregate compute, address-space or filesystem reservation. The two-slot control ledger has bounded logical writes and conservative failure behavior; these runs do not qualify physical storage allocation, power-loss durability or compound terminal-write interruption behavior.

This packet demonstrates an isolated real host CPU-effect component. It does not mount the component into public HMS, qualify a GB10 or other hub's GPU/inference readiness, operate physical I/O or drivers, or install a learned PAT. [NEXT.md](NEXT.md) records those remaining boundaries.
