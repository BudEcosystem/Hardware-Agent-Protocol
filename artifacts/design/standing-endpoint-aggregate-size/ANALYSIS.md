The sealed parent has 146 emitted C bodies totaling 38,606 bytes, plus 554 other text bytes and 26 initialized data bytes: 39,186 flash bytes. Static storage is 1,503 bytes. These are retained failed-link measurements, not a valid ELF or stack qualification. The complete existing inventory is copied under inputs; this packet does not regenerate it.

| Existing emitted owner | Bytes |
| --- | ---: |
| Finite endpoint | 10,160 |
| Standing controller | 15,526 |
| Numeric/serialization kernel | 1,674 |
| Other C owners | 11,246 |
| Other text plus initialized data | 580 |

The four standalone response serializers total only 852 bytes: write_hello 222, write_control 66, write_receipt 176 and standing describe 388. Removing every byte of those bodies for free would still leave 6,078 application bytes. Their nested context/tail/observation helpers occupy another 228 bytes (66/70/92), but are separately retained shared implementations, not duplicated serializer bodies. Serializers alone therefore have insufficient scope.

The actual generated admission_times body has 12 direct predicate calls: three encoded comparisons, two ABSENT checks, four native/encoded comparisons and three elapsed comparisons. Its 300 bytes include 48 call bytes, 56 movw bytes and 52 push/pop bytes. The complete body was read, including the three repeated four-register loads of INT32_MAX before elapsed checks. Those are actual repeated instruction sequences; the 300-byte total does not itself prove removable duplication.

These deliberately impossible free-removal ceilings expose the scope needed; they are not estimates of attainable savings:

| Existing disjoint category | Gross body ceiling | Why it cannot be credited as a saving |
| --- | ---: | --- |
| Four response serializers plus context/tail/observation leaves | 1,080 | Response bytes and all writes still have to be produced; new304-byte codec plans and code are charged |
| admission_times/after_guard, lease_valid, fresh, dispatch_report, context_matches, owns, owns_resources and readiness | 1,608 | Required checks still execute, several retain callback-facing callers, and not every body is replaced by this catalogue |
| Seven containing bodies: finite/standing handlers, OPEN, mutation, admit, accept_observation and loss_service | 10,234 | This includes mandatory state transitions, copies, callbacks, capture and refusal logic, not just repeated field work |

Even free removal of both first categories leaves4,242 application bytes, before adding tables or evaluator code. A meaningful result therefore depends on reductions inside the third category as well. No per-line byte allocation for its pure checks has been established, and the entire10,234-byte containing-body total is only an upper bound, not a removable-code attribution.

The complete finite and standing handlers share the source ordering of transport and boot checks, but their state transitions and counter-exhaustion exceptions differ. Their generated bodies are 1,640 and 1,870 bytes. Standing syntax repeatedly reconstructs four-byte fields and tests the returned registers; its eight-byte reserved-zero check still calls read64 plus a wide comparison. OPEN's 1,656-byte body includes the inlined signed configuration validator, two fence loops, callbacks, fresh authority checks and ownership initialization. Its 13 direct read32 sites are distributed across those distinct tasks. The 1,802-byte mutation body contains 15 such sites; its generated inventory was inspected, but its complete instructions were not manually reread in this continuation.

The retained whole-image inventory reports 107 direct hms_ep_read32 sites, 36 hms_ep_write32 sites and 32 hms_ep_time_cmp_encoded sites. These are static sites, not execution counts, and include other owners. They are not 107 duplicated functions. They identify why sharing a tiny numeric leaf left substantial argument setup, pointer arithmetic, scalar comparison and error-branch code in the callers.

| Complete path group, including newly extracted bodies | Parent phase-size input | Current phase-kernels |
| --- | ---: | ---: |
| admit + admission time phases | 1,556 | 1,614 |
| poll_finite + finite_limits + apply_report | 2,190 | 2,314 |
| standing poll + accept_observation | 1,370 | 1,444 |
| evaluate + dispatch_cutoff | 1,808 | 1,970 |

These groups grew despite smaller individual callers. The new proposal therefore shares ordered work across paths instead of adding another one-caller extraction or blanket noinline rule. It targets pure field comparisons and copy/store scaffolding that occur in both handlers, finite admission, standing OPEN/mutation leases, acquisition and loss verification. Distinct state machines remain explicit C.

There is no evidence-based positive savings estimate. The catalogue adds 1,090 bytes of tables/constants, so at least 8,020 existing bytes must disappear merely to meet the application flash allowance, before accounting for any net new evaluator/access/dispatch/caller code. Whole-image changes can also alter inlining and library retention. This is a demanding test, not an expected outcome. If the result remains above 32,256, the board profile remains unsupported; successful native equality or a smaller caller cannot substitute for that result.

The unchanged runtime owner is 4,668 bytes, including runtime_start 2,148 and clock_snapshot 808. The retained synthetic fixture is 3,120 bytes, including standing_step 1,762. Their cost remains charged. No source changes to those services or their public roots are proposed here. A broader transition/driver/runtime refactor could still be necessary after this experiment; neither this packet nor the prior inline evidence proves that another 6,930 bytes can be removed while preserving all requirements.
