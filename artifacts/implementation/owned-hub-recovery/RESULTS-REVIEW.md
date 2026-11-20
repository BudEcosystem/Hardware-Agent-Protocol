# Recovery increment: executed controls and independent retained-data audit

The root executed all five reviewed control groups successfully. The provider reviewer then source-reviewed and executed only the new independent retained-data audit through its bounded one-child launcher. The audit imported no candidate modules and launched no provider job. Frozen production/control sources, prior attempts, the sealed parent and public baseline remain unchanged.

| Group | Observed assertion checks | Control elapsed seconds | Terminal rows |
| --- | ---: | ---: | ---: |
| structural | 23 | 0.062316 | 1 |
| live | 102 | 2.352825 | 13 |
| faults | 92 | 1.825273 | 13 |
| recovery | 531 | 5.571270 | 33 |
| limits | 50 | 3.417751 | 19 |

These are 798 observed checks, not 798 independent scenarios. Polling adds timing-dependent checks. The 79 terminal rows include one structural ledger fixture; the row count does not mean 79 computations ran. The intentionally invalid successor fixture and empty SIGCHLD-refusal ledger remain explicit evidence rather than successful execution rows.

All five attempt receipts report successful controls, zero exit status, their owned control leader reaped, no remaining observed live process, no pending cleanup interrupt, and stable source/interpreter/public/parent inputs. Their stdout summaries match the retained result records, and stderr is empty. Each attempt's exact frozen pins match both its preserved inputs and current reviewed source.

`AUDIT.json` independently verified 131 canonical state slots, 79 terminal rows, 43 arithmetic results using direct summation, 77 matching free writer-lease inodes and absence of 85 originally observed PID/start-tick identities, including zombies. It verified all 218 sealed parent files, all 244 public baseline files, nine exact original source/helper copies, and recomputed the full source diff. Every retained attempt byte matched the pre-audit snapshot afterward. The prior 866-test suite was not rerun.

The 32 storage/reap combinations cover eight terminal-commit boundaries paired with no reap interruption, a synchronous before-reap exception, a synchronous post-reap exception and pending post-reap SIGINT. All 12 pre-replacement cases reopened conservatively as `unknown`, with no result or exit code. All 20 cases at or after replacement retained their readable, validated terminal `completed` receipt. A separate terminal-reconcile case retained its receipt while releasing its already-reaped live handle. The controls also confirmed poisoned-state refusal of a fresh key while original-key replay remained available.

The limits group retained a bootstrap exit 74 before release, a post-release `WALL_LIMIT` failure, the CPU-limit observation and sixteen completed retained keys. The seventeenth key was refused and all sixteen historical keys replayed. The CPU fixture's installed leader reported its computation child terminated by signal 9 and consumed 1.00013 CPU seconds, then reaped it. The provider recorded the resulting process failure rather than validated output. These remain per-process limits and serviced wall observations, not aggregate reservations or real-time guarantees.

The bounded audit exited zero with its sole audit child reaped, no stderr, no pending cleanup signals and stable audit/runtime inputs. Its report SHA256 is `26981871565c4f511e99cf4e3d26d32fdb6370aeb3f7665c61d5b08057867a32`; `audit-attempt-1/` retains the reviewed source copies, intent, stdout/stderr and launcher receipt. [AUDIT-SOURCE-REVIEW.md](AUDIT-SOURCE-REVIEW.md) describes its read-only evidence scope and bounds.

These results qualify the executed orderly failure paths. The storage controls inject exceptions at named boundaries; they do not fill a filesystem, simulate loss of power or establish durability after a device crash. The original provider owner is not killed here. A current readable terminal slot after replacement is not proof that the rename would survive power loss. Lease quiescence and bounded process observations do not prove universal descendant enumeration or containment. This packet's own execution scope remains orderly failure controls.

Separate [provider-owner-death evidence](../owned-hub-crash-harness/README.md) now passes twelve cases in 1.960245488 observed wall seconds, reaping twenty controlled children plus the outer control process. Its outcomes are six `not_started`, three `unknown` and three retained `completed` receipts. All twelve initial writer leases were free, so that run does not deliberately cover retained-writer deferral. Those actual owner-death results belong to the separate harness. No public provider mount, qualified aggregate/control-storage admission, GPU/GB10 inference capability, physical I/O/driver control or learned PAT installation is added by this recovery packet. [NEXT.md](NEXT.md) records the remaining joins.
